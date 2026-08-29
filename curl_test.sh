#!/bin/bash
# Run this ON THE SERVER to test panel auth step by step
# Usage: bash curl_test.sh

URL="https://45.43.77.169:1488/8spqLzfgXxcUlggSB8"
USER="ILvi7QdOnD"
PASS="vmTHQlc1k1"

echo "=== Step 1: GET / and save cookie ==="
COOKIE=$(curl -k -s -D - "$URL/" -o /dev/null | grep -i 'set-cookie' | head -1 | sed 's/Set-Cookie: //I' | cut -d';' -f1 | tr -d '\r\n')
echo "Cookie: $COOKIE"

echo ""
echo "=== Step 2: POST /login with JSON ==="
curl -k -v -X POST "$URL/login" \
  -H "Content-Type: application/json" \
  -H "Cookie: $COOKIE" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Origin: $URL" \
  -H "Referer: $URL/" \
  -d "{\"username\":\"$USER\",\"password\":\"$PASS\"}" \
  2>&1

echo ""
echo "=== Step 3: POST /login with FORM ==="
curl -k -v -X POST "$URL/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Cookie: $COOKIE" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Origin: $URL" \
  -H "Referer: $URL/" \
  -d "username=$USER&password=$PASS" \
  2>&1
