#pragma extern asm

int ANSWER = 0;


int fibonacci(int a) {
    if (a <= 1) {
        return a;
    }

    return fibonacci(a - 1) + fibonacci(a - 2);
}


int main() {
    ANSWER = fibonacci(5);
}
