"""Repository layer package.

Repositories encapsulate all database access for a given domain entity.
They expose a small, intention-revealing API (e.g. `get_by_email`) and
hide SQLAlchemy specifics from the service layer.
"""
