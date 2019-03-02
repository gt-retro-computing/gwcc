#pragma extern asm

#define left(b) ((int*)*b)
#define right(b) ((int*)*(b+1))
#define data(b) *(b+2)

int checkTreeEquality(int* b1, int* b2)
{
    if (!b1 && !b2) {
        return 1;
    }

    if (b1 && b2) {
        if (data(b1) != data(b2)) return 0;
        else if (!checkTreeEquality(left(b1), left(b2))) return 0;
        else if (!checkTreeEquality(right(b1), right(b2))) return 0;
        else return 1;
    }

    return 0;
}

int main;