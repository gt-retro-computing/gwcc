#pragma extern asm

#pragma location 0x4000
int a;

int c;

int main() {

    int x = 5;
    int y = 6;

    if (x > 0) {
        a = 7;
    }

    if (x >= 0) {
        a = 7;
    }

    if (x < 0) {
        a = 7;
    }

    if (x <= 0) {
        a = 7;
    }


}