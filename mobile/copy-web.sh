#!/usr/bin/env bash
set -e
rm -rf www && mkdir -p www
cp -r ../app/* www/
echo "Web assets copied to mobile/www"
