#pragma extern asm


int* ARRAY = 0x5000;
int LEN = 6;
int CHECKPOINT1,CHECKPOINT2,CHECKPOINT3;

void main() {
    CHECKPOINT1 = ARRAY[LEN-1];
    if (CHECKPOINT1 < 0) {
        CHECKPOINT2 = -1;
        int i = 0;
        int sum = 0;
        while (i < LEN) {
            int val = ARRAY[i];
            if (val < 0) {
                sum += val;
            }
            i++;
        }
        CHECKPOINT3 = sum;
    } else if (CHECKPOINT1 > 0) {
        CHECKPOINT2 = 1;
        int sum = 0;
        int i =0;
        while (i < LEN) {
            int val = ARRAY[i];
            if (val > 0) {
                sum += val;
            }
            i++;
        }
        CHECKPOINT3 = sum;
    } else {
        CHECKPOINT2 = 0;
        CHECKPOINT3 = 0;
    }
}
