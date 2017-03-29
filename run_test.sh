#!/usr/bin/env bash

# create test directories
rm -rf test_source
rm -rf test_target
mkdir -p test_source
cp archive.py test_source/f1.py
cp archive.py test_source/f2.py
mkdir -p test_source/f3
cp README.md test_source/f3
cp archive.py test_source/f3/e1.py
# an unreadable file
chmod 200 test_source/f3/e1.py 

mkdir -p test_target

# now run the test
echo "dry run"
python archive.py --source ./test_source/ --target ./test_target/ --verbose --dry

echo "real run 1"
python archive.py --source ./test_source/ --target ./test_target/ --verbose

echo "real run 2"
python archive.py --source ./test_source/ --target ./test_target/ --verbose --min_size 128 --copy
