#!/bin/bash
set -e

docker -v >/dev/null

dockerExists=$?

if  [ $dockerExists != 0 ]; then
	echo ERROR: Please install Docker before running this script. Refer to the CS 2110 Docker Guide.
	exit 1
fi

docker container ls >/dev/null
dockerNotRunning=$?

if [ $dockerNotRunning != 0 ]; then
	echo ERROR: Docker is not currently running. Please start Docker before running this script.
	exit 1
fi

run_grader() {
    test_results=$(mktemp)

    docker run --rm -it -v "$(pwd)":/autograder/submission/ $1 /bin/sh -c '/autograder/run_local' | tee ${test_results}

    num_fails=$(grep 'FAILED' ${test_results} | wc -l)
    if [[ ${num_fails} -gt 0 ]]; then
        echo 'ERROR: tests failed'
        exit 1
    fi
}


python main.py testcases/gates.c
python main.py testcases/reverse.c
python main.py testcases/phone.c
python main.py testcases/linkedlist.c

run_grader "gtcs2110/hw6-spring19"

python main.py testcases/fibonacci.c

run_grader "gtcs2110/lab13-spring19"


echo 'Tests Succeeded!'
