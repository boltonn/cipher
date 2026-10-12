"""Parsers for message and record formats -- email, calendar, contacts, HTML -- as plain functions.

Each format exposes `parse_*` (and `iter_*` for files holding many records). Child files go to a
caller-supplied `ChildSink` (`pyparse.children`); nothing here decides where bytes are stored.
"""
