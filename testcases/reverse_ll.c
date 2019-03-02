#pragma extern asm

#define next(n) ((int*)*n)

int* reverse(int* head)
{
    if (!head || !next(head)) {
        return head;
    }

    int* new_head = reverse(next(head));
    int* thang = next(head);
    *thang = (int)head;
    *head = 0;

    return new_head;
}

int main;
