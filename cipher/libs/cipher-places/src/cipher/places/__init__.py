"""Offline gazetteer: resolve a place-name mention to one canonical country / admin1 / city / region."""

from cipher.places.gazetteer import Gazetteer, Place, PlaceKind, default_data_dir, default_gazetteer_path, place_key

__all__ = ["Gazetteer", "Place", "PlaceKind", "default_data_dir", "default_gazetteer_path", "place_key"]
