import time
import logging
from django.db import connection

logger = logging.getLogger(__name__)

class QueryLoggingMiddleware:
    """
    Middleware that logs the number of queries and total execution time for each request.
    This helps identify N+1 query issues and slow endpoints.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # We only want to log in debug mode or if explicitly enabled
        start_time = time.time()
        
        # Keep track of queries before this request
        initial_queries = len(connection.queries)

        response = self.get_response(request)

        # Calculate time and queries
        total_time = time.time() - start_time
        final_queries = len(connection.queries)
        queries_run = final_queries - initial_queries

        if queries_run > 0:
            # You can adjust the threshold for what constitutes a "slow" request
            # or a request with "too many" queries.
            if queries_run > 20 or total_time > 0.5:
                logger.warning(
                    f"SLOW/HEAVY REQUEST: {request.method} {request.path} "
                    f"- {queries_run} queries in {total_time:.3f}s"
                )
            else:
                logger.debug(
                    f"{request.method} {request.path} "
                    f"- {queries_run} queries in {total_time:.3f}s"
                )

        return response
