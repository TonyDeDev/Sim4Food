function CafeIcon() {
  return <><path d="M4 9h13v5.5A4.5 4.5 0 0 1 12.5 19h-4A4.5 4.5 0 0 1 4 14.5V9Z" /><path d="M17 10h1.5a2.5 2.5 0 0 1 0 5H17M7 5c0 1 1 1 1 2m4-3c0 1 1 1 1 2" /><path d="M3 21h16" /></>
}

function BakeryIcon() {
  return <><path d="M4 10.5c0-2.5 2-4.5 4.5-4.5 1.3 0 2.4.5 3.2 1.4A4.5 4.5 0 0 1 20 10.5V18H4v-7.5Z" /><path d="M8 9.5v4m4-5v5m4-4v4M3 20h18" /></>
}

function RestaurantIcon() {
  return <><path d="M6 3v6m3-6v6m-6-3h6m-3 3v11" /><path d="M16 3v7a3 3 0 0 0 3 3V3m-3 7h3v9" /></>
}

function MarketIcon() {
  return <><path d="M4 9h16l-1.5 11h-13L4 9Z" /><path d="m7 9 3-5m7 5-3-5M3 9h18M8 13v3m4-3v3m4-3v3" /></>
}

function TruckIcon() {
  return <><path d="M3 6h11v11H3zM14 10h4l3 3v4h-7" /><circle cx="7" cy="18" r="2" /><circle cx="18" cy="18" r="2" /><path d="M5 9h7" /></>
}

function StoreIcon() {
  return <><path d="M4 10v10h16V10M3 10l2-6h14l2 6" /><path d="M3 10a2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0 5 0 2 2 0 0 0 4 0M9 20v-6h6v6" /></>
}

export default function BusinessTypeIcon({ type = '' }) {
  const normalized = type.toLocaleLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  let icon = <StoreIcon />

  if (/cafe|coffee|tea room|coffee shop/.test(normalized)) icon = <CafeIcon />
  else if (/bakery|baker|patisserie|pastry|cake shop/.test(normalized)) icon = <BakeryIcon />
  else if (/restaurant|diner|bistro|eatery|dining/.test(normalized)) icon = <RestaurantIcon />
  else if (/food truck|cater|mobile food/.test(normalized)) icon = <TruckIcon />
  else if (/grocery|grocer|market|supermarket|produce|convenience/.test(normalized)) icon = <MarketIcon />

  return (
    <svg className="business-type-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {icon}
    </svg>
  )
}
