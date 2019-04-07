# The Gangweed C Compiler

This C compiler was created as a meme for our systems architecture class where they wanted us to write assembly in some terrible ISA called LC-3.
In this class, it's sometimes necessary to "demo" your homework in-person in front of a TA. We decided it would be funny if we turned in our homework
as unreadable compiler-generated assembly.
Originally, we were going to make it support multiple architectures (namely 8080) but then I realized that it will never self-host because it's in Python.
It needs to be rewritten in C anyways. Currently it only supports one backend, LC-3. Internally, it operates on an IR form. The code generation and register
allocation are both pretty horrible because I just wanted to get my homework done.
