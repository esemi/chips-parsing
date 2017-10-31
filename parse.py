#! /usr/bin/env python
# -*- coding: utf-8 -*-

import time
from collections import deque
from itertools import product

import asyncio
import aiohttp

from config import VALID_CODE, URL, MAX_CLIENTS, CODE_PREFIX, DEBUG, CODE_CHARS

# todo stats
# todo bound_fetch


# todo db for storage ?
class Storage(object):

    codes = deque()

    def __init__(self):
        combination_len = len(VALID_CODE) - len(CODE_PREFIX)
        log('Generate code by len %s' % combination_len)
        for comination in product(CODE_CHARS, repeat=combination_len):
            print(comination)
            code = '%s%s' % (CODE_PREFIX, ''.join(comination))
            log('add code %s' % code)
            self.codes.append(code)
        log('Gen %d codes' % len(self.codes))

    def get_code_for_check(self):
        return self.codes.pop()

    def save_parsed_code(self, code: str, valid: bool):
        pass


def log(msg):
    # todo use logging
    if DEBUG:
        print(msg)


async def task(pid, storage: Storage):
    log('Fetch async process {} started'.format(pid))
    start = time.time()
    try:
        code1 = storage.get_code_for_check()
    except IndexError:
        code1 = ''

    try:
        code2 = storage.get_code_for_check()
    except IndexError:
        code2 = ''

    async with aiohttp.ClientSession() as session:
        async with session.post(URL, data={'codes': [VALID_CODE, code1, code2]}) as resp:
            response_json = await resp.json()
            log(response_json)
            log('Process {}: {} {} {}, took: {:.2f} seconds'.format(
                pid, code1, code2, response_json, time.time() - start))
            # todo parse response and save results


async def run():
    storage = Storage()
    start = time.time()
    tasks = [asyncio.ensure_future(task(i, storage)) for i in range(1, MAX_CLIENTS + 1)]
    await asyncio.wait(tasks)
    log("Process took: {:.2f} seconds".format(time.time() - start))


if __name__ == '__main__':
    log('Asynchronous:')
    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(run())
    ioloop.close()
