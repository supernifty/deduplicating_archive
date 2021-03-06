#!/usr/bin/env python
'''
  Deduplicating archiver
  Copies files to a target dir and generates symlinks in the original file positions
  Duplicate files point to the same file
  A sqlite database tracks all generated symlinks

  Example usage: python archive.py --source ./test_source/ --target ./test_target/ --verbose --dry
'''

import argparse
import datetime
import hashlib
import logging
import os
import parser
import shutil
import stat
import sys
import sqlite3

BLOCKSIZE=65536 # when reading files
MIN_SIZE=1024 # min size of file to archive
UPDATE_PERIOD=10 # how often to log progress

CHECK_BYTES=True # also look at head of file content when comparing
USE_COPY=False

def check_bytes(first_buf, target_file):
    '''
      additional check as well as hash
    '''
    with open(target_file, 'rb') as fh:
        target_buf = fh.read(BLOCKSIZE)

    return first_buf == target_buf


def archive(source_dir, target_dir, dry, min_size=MIN_SIZE, copy=USE_COPY):
    # open db  
    conn = sqlite3.connect(os.path.join(target_dir, 'db.sqlite'))
    c = conn.cursor()
    c.execute('create table if not exists link (source text, target text, added integer)')
    conn.commit()
 
    # find all candidates for archival
    considered = 0
    added = 0
    source_size = 0
    saved_size = 0
    dry_archive = set()
    
    absolute_source = os.path.abspath(source_dir)
    absolute_target = os.path.abspath(target_dir)

    last_update = datetime.datetime.now()
    logging.info('archiving %s to %s', absolute_source, absolute_target)

    for root, dirnames, filenames in os.walk(absolute_source, followlinks=True):
        for filename in filenames:
            considered += 1
            if datetime.datetime.now() - last_update > datetime.timedelta(seconds=UPDATE_PERIOD):
                logging.info('added %i files, considered %i files, total size %i bytes, saved size %i bytes', added, considered, source_size, saved_size)
                last_update = datetime.datetime.now()

            source_file = os.path.join(root, filename)
            if os.path.islink(source_file):
                logging.debug('skipping %s: is a symlink', source_file)
                continue

            logging.debug('processing %s', source_file)

            # find the hash of this file
            file_size = os.stat(source_file).st_size
            source_size += file_size
            if file_size < min_size:
                logging.debug('skipping %s: file size is %i, smaller than %i', source_file, file_size, min_size)
                continue

            try:
                hasher = hashlib.sha256()
                with open(source_file, 'rb') as fh:
                    first_buf = buf = fh.read(BLOCKSIZE)
                    while len(buf) > 0:
                        hasher.update(buf)
                        buf = fh.read(BLOCKSIZE)
                h = hasher.hexdigest()
                target_file = os.path.join(absolute_target, h[:2], h)
                if os.path.exists(target_file) and file_size == os.stat(target_file).st_size or dry and h in dry_archive: # we can symlink to the existing file
                    if dry:
                        logging.debug('would create symlink to existing file: %s -> %s', target_file, source_file)
                    else:
                        if CHECK_BYTES and not check_bytes(first_buf, target_file):
                            logging.error('skipping %s: check_bytes failed.', source_file)
                            continue

                        os.remove(source_file)
                        os.symlink(target_file, source_file)
                        c.execute('insert into link (source, target, added) values (?, ?, ?)', (source_file, target_file, datetime.datetime.now()))
                        conn.commit()
                        logging.debug('symlink to existing file: %s -> %s', source_file, target_file)
                    saved_size += file_size
                else: # mv the file to the archive
                    if dry:
                        logging.debug('would move file to archive: %s -> %s', source_file, target_file)
                        dry_archive.add(h)
                    else:
                        if not os.path.exists(os.path.join(absolute_target, h[:2])):
                            os.makedirs(os.path.join(absolute_target, h[:2]))
                        if copy:
                            shutil.copy(source_file, target_file)
                            os.remove(source_file)
                        else:
                            shutil.move(source_file, target_file)
                        current = stat.S_IMODE(os.lstat(target_file).st_mode)
                        os.chmod(target_file, current & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH) # make the file read only
                        os.symlink(target_file, source_file) # link to it
                        c.execute('insert into link (source, target, added) values (?, ?, ?)', (source_file, target_file, datetime.datetime.now()))
                        conn.commit()
            except IOError as ex:
                logging.warn('skipping %s: exception: %s', source_file, ex)
                continue
            added += 1
    logging.info('done archiving %s to %s: %i added out of %i files considered. total size considered %i bytes, saved %i bytes', absolute_source, absolute_target, added, considered, source_size, saved_size)
                

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Archive files and deduplicate')
    parser.add_argument('--source', nargs='+', required=True, help='source directory containing files to archive')
    parser.add_argument('--target', required=True, help='target directory where files will be copied to')
    parser.add_argument('--dry', action='store_true', help='just log what would be done')
    parser.add_argument('--verbose', action='store_true', help='include more logging')
    parser.add_argument('--min_size', type=int, default=1024, help='minimum file size to archive')
    parser.add_argument('--copy', action='store_true', default=False, help='copy/rm files instead of moving')
    
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.DEBUG)
    else:
        logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

    logging.info('starting archiver with parameters %s...', sys.argv)
    for source in args.source:
        archive(source, args.target, args.dry, args.min_size, args.copy)

