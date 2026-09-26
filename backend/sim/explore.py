"""Exploratory analysis of the demo data. Prints the numbers that drive waste.py and calibrate.py."""
import pandas as pd

from ingest import load_workbook

pd.set_option("display.width", 200)


def weekly_usage(d):
    s = d["sales"].merge(d["recipes"], on="item_id")
    s["use"] = s["qty_sold"] * s["qty_per_serving"]
    s["week"] = (s["date"] - s["date"].min()).dt.days // 7
    return s.groupby(["week", "ingredient_id"])["use"].sum().unstack()


def waste_table(d):
    start = d["sales"]["date"].min()
    week = lambda x: (x - start).dt.days // 7
    use = weekly_usage(d)
    pur = d["purchases"].assign(week=week(d["purchases"]["date"]))
    pur = pur.groupby(["week", "ingredient_id"])["qty"].sum().unstack()
    cnt = d["inventory_counts"].assign(week=week(d["inventory_counts"]["date"]))
    close = cnt.groupby(["week", "ingredient_id"])["qty_on_hand"].sum().unstack()
    opening = close.shift(1)  # week 0 has no opening count
    waste = opening + pur - close - use
    return waste.iloc[1:], use, pur, close


def main():
    d = load_workbook()
    cost = d["ingredients"].set_index("ingredient_id")["unit_cost"]
    waste, use, pur, close = waste_table(d)

    print("== Waste per ingredient, weeks 1-11 (units, $)")
    tot = waste.sum()
    out = pd.DataFrame({"waste_units": tot.round(1), "waste_$": (tot * cost).round(2),
                        "pct_of_purchased": (tot / pur.loc[1:].sum() * 100).round(1)})
    print(out.sort_values("waste_$", ascending=False))
    print("total $", round((tot * cost).sum(), 2))
    print("negative weekly cells:", int((waste < -0.5).sum().sum()), "of", waste.size)
    print("\n== Weekly waste $")
    print((waste * cost).sum(axis=1).round(2).to_string())

    print("\n== Weekday profile (avg dishes/day)")
    s = d["sales"]
    day = s.groupby("date")["qty_sold"].sum()
    print(day.groupby(day.index.day_name()).mean().round(0).reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]).to_string())

    print("\n== Event lift (vs mean of same weekday on non-event days)")
    ev = d["events"]
    ev_days = set()
    for _, e in ev.iterrows():
        ev_days |= set(pd.date_range(e.start_date, e.end_date))
    base = day[~day.index.isin(ev_days)]
    base_dow = base.groupby(base.index.dayofweek).mean()
    for _, e in ev.iterrows():
        days = [x for x in pd.date_range(e.start_date, e.end_date) if x in day.index]
        if not days:
            print(f"{e['name']}: after data window (upcoming)")
            continue
        tot_lift = sum(day[x] / base_dow[x.dayofweek] for x in days) / len(days)
        line = f"{e['name']}: total traffic x{tot_lift:.2f}"
        if e["type"] == "deal":
            it = e["items"]
            isales = s[s.item_id == it].set_index("date")["qty_sold"]
            ib = isales[~isales.index.isin(ev_days)]
            ibd = ib.groupby(ib.index.dayofweek).mean()
            ok = [x for x in days if x in isales.index]  # skip sold-out days (censored)
            line += (f", {it} x{sum(isales[x] / ibd[x.dayofweek] for x in ok) / len(ok):.2f}"
                     f" (excl. {len(days) - len(ok)} sold-out day)")
        print(line)

    print("\n== Owner rule check: order = last7 usage x 1.25 - stock, rounded up to pack")
    pack = d["ingredients"].set_index("ingredient_id")["pack_size"]
    weekly_bought = pur.loc[2:11]
    est = (use.shift(1) * 1.25 - close.shift(1)).loc[2:11]
    ratio = (weekly_bought.sum() / est.clip(lower=0).sum()).round(2)
    print(ratio.to_string())

    print("\n== Fish/chicken sanity: Sunday counts")
    print(close[["fish_fillet", "chicken"]].T.to_string())


if __name__ == "__main__":
    main()
