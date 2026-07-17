from fees.grid_views import get_grid_data
from django.http import HttpRequest
import json

class DummyRequest:
    def __init__(self):
        self.headers = {'X-Company': 'LP'}
        self.query_params = {}

req = DummyRequest()
try:
    data, max_p = get_grid_data(req)
    print("Success. Records:", len(data), "Max Payments:", max_p)
except Exception as e:
    import traceback
    traceback.print_exc()
