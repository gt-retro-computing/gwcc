#pragma extern asm

int* ARRAY = 0x4000;
unsigned int LENGTH = 7;

void main() {
    unsigned x = 0; // 1st index of the array
    unsigned y = LENGTH - 1; // last index of the array
    while (x < y) {
        int temp = *(ARRAY+x);
        *(ARRAY+x) = *(ARRAY+y);
        *(ARRAY+y) = temp;
        x++;
        y--;
    }
}

#pragma location 0x4000
int a = 1;
int a1 = 2;
int a2 = 3;
int a3 = 4;
int a4 = 5;
int a5 = 6;
int a6 = 7;
