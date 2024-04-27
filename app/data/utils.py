data_store = {'scopus': None, 'wos': None, 'processed': None}

from functools import wraps
from flask import session, redirect, url_for