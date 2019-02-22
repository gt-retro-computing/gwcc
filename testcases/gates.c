#pragma extern asm

unsigned int A = 63090, B = 14233, X = 19253;
unsigned int ANSWER;

void main() {
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
