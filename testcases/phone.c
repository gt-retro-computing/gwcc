#pragma extern asm

#pragma location 0x4000
char* input = "(704) 555-2110";

#pragma location 0x3100
char* STRING = input;
int ANSWER;
int main() {
    char* s = STRING;
    if (*(s++) != '(') return ANSWER = 0;

    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;
    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;
    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;

    if (*(s++) != ')') return ANSWER = 0;
    if (*(s++) != ' ') return ANSWER = 0;

    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;
    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;
    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;

    if (*(s++) != '-') return ANSWER = 0;

    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;
    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;
    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;
    if (*s > '9' || *s < '0') return ANSWER = 0;
    s++;

    if (*s != '\0') return ANSWER = 0;

    return ANSWER = 1;
}

