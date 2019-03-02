#pragma extern asm

int strlen(char* s)
{
    int length = 0;
    while (*s) {
        s++;
        length++;
    }
    return length;
}

int decimalStringToInt(char* decimal)
{
    int ret = 0;
    int i = 0;
    while (i < strlen(decimal)) {
        ret *= 10;
        ret += decimal[i] - '0';
        i++;
    }
    return ret;
}

int main;
