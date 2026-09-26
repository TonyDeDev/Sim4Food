"""Computes historical waste and dollar loss per ingredient.

waste = start stock + purchases - end stock - (dishes sold x recipe qty)
"""


def compute_waste(restaurant_id: str) -> dict:
    raise NotImplementedError
