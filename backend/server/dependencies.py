"""This module contains the dependencies for the server."""

def get_db():
    """Get the database connection."""
    db_instance = "Dummy database connection"
    try:
        yield db_instance
    finally:
        pass # close the database connection if necessary