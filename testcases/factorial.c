int fac(int n) {
    int result = 1;
    int i = 1;
    while (i < n || i == n) {
        result *= i;
        i++;
    }
    return result;
}

int main() {
    return fac(7);
}