//#pragma location 0x4000
//typedef struct {
//    int a;
//} shit;
//
//#define asdf 234
//
////#pragma location 0x4000
//
//typedef int uintptr_t;
//
//uintptr_t value;
//
//unsigned lol;
//
//int value3 = 69;

//int value4 = (short)6;
//int foo() {
//    return 5;
//}

#pragma extern asm
unsigned int A = 63090, B = 14233, X = 19253;
unsigned int ANSWER;
int main() {

    A++;
    int x = sizeof(long);

    int *y = 5;

    *y = (int)6;

    ANSWER = 0;
    if ((A > X) && (B < X))
        ANSWER = ~(A & B);
    else if ((A > X) && (B > X))
        ANSWER = ~(A | B);
    else if ((A < X) && (B < X))
        ANSWER = A | B;
    else if ((A < X) && (B > X))
        ANSWER = A & B;
    else
        ANSWER = ~A;
}

//int main(int argc, char** argv) {
//int cock;
//    char* test = *argv;
//    long meme;
////    int(*fucker)() =foo;
//    long* lol = &meme;
//    lol += asdf;
//    int wowza = value3+6969+sizeof(int);
//
//    typedef unsigned int int2;
//    int2 x = 3*(5+5),y;
//    char z = 5;
//    z;
//    int* ptr = 5;
//    int hottestMeme;
//    {
//    int zozzle = *ptr;
//    z++;
//    if(0);
//    int lolz = ++z;
//    lolz = (*ptr)++;
//    ptr++;
//    ptr += 777;
//    int lol = *ptr += 0x888;
//    z = (x = y);
//    hottestMeme=lolz+lol+zozzle;
//    }
//    if (1) while (1) {
//    continue;
//    }
//    while (1) { break; }
////    for (;;);
////    for (;;){;}
////    for (int i = 0; i < 5; i++);
//    if (1+1 == 2) {
//        y = 3;
//        x++;
//    } else if (!!z) {
//        y = 5;
//        *ptr = 3;
//    }
//    return y*(x+z)+hottestMeme+wowza;
////    return 0;
//}

//
//int bar() {
//    return 6;
//}



