#!/bin/bash
if ! docker images | grep -q "wordguess"; then
  docker build -t wordguess . && docker image prune
fi
docker run -v $PWD:/app -it -p 5000:5000 wordguess bash
