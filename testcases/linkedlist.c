#pragma extern asm

int DATA = 10;
int* LL = 0x6000;

void main() {
    int length = *(LL+1);
    int* curr = (int*)*(LL);
    while (curr) {
        if (*(curr+1) == DATA) {
            *(curr+1) = length;
        }
        curr = (int*)*(curr);
    }
}
