# ############################################################################## #
# Created by Polterx, on Saturday, 1st of July, 2023                             #
# Website https://poltersanctuary.com                                            #
# Github  https://github.com/PolterEnterprise                                    #
# ############################################################################## #

import time
import threading

class RateLimiter:
    def __init__(self, delay):
        self.delay = delay
        self.lock = threading.Lock()
        self.last_request_time = time.perf_counter()

    def wait(self):
        with self.lock:
            try:
                elapsed_time = time.perf_counter() - self.last_request_time
                if elapsed_time < self.delay:
                    remaining_time = self.delay - elapsed_time
                    time.sleep(remaining_time)
                self.last_request_time = time.perf_counter()
            except Exception as e:
                print(f"RateLimiter encountered an error: {e}")
                raise

    def __enter__(self):
        self.wait()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # print(f"RateLimiter encountered an error during exit: {exc_val}")
            # return False to propagate the exception if it's KeyboardInterrupt
            return False if exc_type is KeyboardInterrupt else True
