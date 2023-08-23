#!/bin/bash

SERIAL_PORT=$1

while true
do
 
   cat $2 > $SERIAL_PORT
   sleep 1

   cat $3 > $SERIAL_PORT
   sleep 1

   cat $3 > $SERIAL_PORT
   sleep 1

 done
