#pragma extern asm

int function(int a, int b) {
    return a + b;
}

int main() {
    int x = 1+2+3+4+5+6+7+8+9+10;
    int y = function(1, 2);
    return x+y;
}