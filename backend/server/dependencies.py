"""
This module contains the dependencies for the server.
"""

def get_db():
    db_instance = "Dummy database connection"
    try:
        yield db_instance
    finally:
        pass
