# ############################################################################## #
# Created by Polterx, on Saturday, 1st of July, 2023                             #
# Website https://poltersanctuary.com                                            #
# Github  https://github.com/PolterEnterprise                                    #
# ############################################################################## #

import time

class RateLimiter:
    def __init__(self, delay):
        self.delay = delay
        self.last_request_time = 0

    def wait(self):
        elapsed_time = time.time() - self.last_request_time

        if elapsed_time < self.delay:
            time.sleep(self.delay - elapsed_time)

    def __enter__(self):
        elapsed_time = time.time() - self.last_request_time

        if elapsed_time < self.delay:
            remaining_time = self.delay - elapsed_time
            time.sleep(remaining_time)
            self.last_request_time = time.time()

    def __exit__(self, *args):
        self.last_request_time = time.time()
