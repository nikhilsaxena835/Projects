/*
REFERENCES
https://stackoverflow.com/questions/13421424/how-to-evaluate-an-infix-expression-in-just-one-scan-using-stacks
*/
#include <iostream>
#include <string>

using namespace std;

/*
Operator stack is initially set to 3000 (good will assumption) but can resize so its safe. Stack copying is done
manually so shallow copy no issue. Same goes for operand stack. Only relevant operations implemented.
*/

class OpStack {
    char* arr;      
    int idx;          
    int max_size;     

public:
    OpStack(int size = 3000) : idx(-1), max_size(size) 
    {
        arr = new char[size];
    }

    ~OpStack() { delete[] arr; }

    void resize() {
        int new_size = max_size * 2;
        char* new_arr = new char[new_size];
        for (int i = 0; i <= idx; i++) {
            new_arr[i] = arr[i];
        }
        delete[] arr;
        arr = new_arr;
        max_size = new_size;
    }

    bool empty() const { return idx == -1; }
    void push(char c) {
        if (idx == max_size - 1) resize();
        arr[++idx] = c;
    }
    char pop() { return arr[idx--]; }
    char top() const { return arr[idx]; }
};

class StringStack {
    string* arr;
    int idx;
    int max_size;

public:
    StringStack(int size = 3000) : idx(-1), max_size(size) 
    {
        arr = new string[size];
    }
    
    ~StringStack() { delete[] arr; }

    void resize() {
        int new_size = max_size * 2;
        string* new_arr = new string[new_size];
        for (int i = 0; i <= idx; i++) 
        {
            new_arr[i] = arr[i];
        }
        delete[] arr;
        arr = new_arr;
        max_size = new_size;
    }

    void push(const string& s) {
        if (idx == max_size - 1) resize();
        arr[++idx] = s;
    }
    string pop() { return arr[idx--]; }
    bool empty() const { return idx == -1; }
};

int compareStrings(const string& str1, const string& str2) {
    if (str1.size() != str2.size())
        return str1.size() < str2.size() ? -1 : 1;
        
    for (int i = 0; i < str1.size(); i++) {
        if (str1[i] != str2[i])
            return str1[i] < str2[i] ? -1 : 1;
    }
    return 0;
}

string add(string a, string b) {
    int n = max(a.size(), b.size());
    int carry = 0;

    char result[n + 2]; 
    int index = n;      
    result[index + 1] = '\0'; 

    while (a.size() < n) a = "0" + a;
    while (b.size() < n) b = "0" + b;

    for (int i = n - 1; i >= 0; --i, --index) 
    {
        int sum = (a[i] - '0') + (b[i] - '0') + carry;
        carry = sum / 10;
        result[index] = (sum % 10) + '0'; 
    }

    if (carry) 
    {
        result[index] = carry + '0';
        return string(result + index); 
    }

    return string(result + index + 1);
}

/*
A>=B is assumed from the problem. Rest all are standard implementations like Euclid, long division.
*/
string sub(string a, string b) {
    int n = a.size();
    int borrow = 0;

    char result[n + 1]; 
    result[n] = '\0';   

    while (b.size() < n) b = "0" + b;

    for (int i = n - 1; i >= 0; i--) {
        int digit = (a[i] - '0') - (b[i] - '0') - borrow;
        if (digit < 0) {
            digit += 10;
            borrow = 1;
        } else {
            borrow = 0;
        }
        result[i] = digit + '0'; 
    }
    int start = 0;
    while (start < n && result[start] == '0') start++;

    return (start == n) ? "0" : string(result + start);
}

string mul(string& a, string& b) {
    int n = a.size(); 
    int m = b.size();
    int resultSize = n + m;

    char result[resultSize + 1]; 
    fill(result, result + resultSize, '0');
    result[resultSize] = '\0';              

    for (int i = n - 1; i >= 0; i--) {
        int carry = 0;
        for (int j = m - 1; j >= 0; j--) {
            int product = (a[i] - '0') * (b[j] - '0') + (result[i + j + 1] - '0') + carry;
            result[i + j + 1] = (product % 10) + '0'; 
            carry = product / 10;                    
        }
        result[i] += carry; 
    }

    int start = 0;
    while (start < resultSize && result[start] == '0') start++;

    return (start == resultSize) ? "0" : string(result + start);
}

string div(string a, string b) {
    if (compareStrings(a, b) < 0) return "0";

    int n = a.size();
    char quotient[n + 1]; 
    quotient[n] = '\0';    

    string current = "";   

    for (int i = 0; i < n; i++) 
    {
        current += a[i];   
        while (current.size() > 1 && current[0] == '0') 
            {
                current = current.substr(1); }

        int count = 0;
        while (compareStrings(current, b) >= 0) 
        {
            current = sub(current, b);
            count++;
        }
        quotient[i] = count + '0';
    }

    int start = 0;
    while (start < n && quotient[start] == '0') {start++;}

    return (start == n) ? "0" : string(quotient + start);
}

string mod(string a, string b) {
    if (compareStrings(a, b) < 0) return a;
    
    string current;
    current.reserve(a.size());
    
    for (char digit : a) {
        current += digit;
        while (current.size() > 1 && current[0] == '0')
            current = current.substr(1);
            
        while (compareStrings(current, b) >= 0)
            current = sub(current, b);
    }
    
    return current.empty() ? "0" : current;
}

string gcd(string a, string b) {
    while (b != "0") {
        string temp = b;
        b = mod(a, b);
        a = temp;
    }
    return a;
}

string exp(string base, string power) {
    if (power == "0") return "1";
    if (base == "0") return "0";
    if (base == "1") return "1";
    
    string result = "1";
    while (power != "0") {
        if ((power.back() - '0') % 2 == 1)
            result = mul(result, base);
        
        base = mul(base, base);
        
        string newPower;
        int carry = 0;
        for (int i = 0; i < power.size(); i++) {
            int curr = (power[i] - '0') + carry * 10;
            newPower += (curr / 2) + '0';
            carry = curr % 2;
        }
        
        int start = newPower.find_first_not_of('0');
        power = (start != string::npos) ? newPower.substr(start) : "0";
    }
    return result;
}

string fact(string& number) {
    if (number == "0" || number == "1") return "1";
    
    string result = "1";
    string current = "1";
    string limit = add(number, "1");
    
    while (current != limit) {
        result = mul(result, current);
        current = add(current, "1");
    }
    return result;
}

int getPrecedence(char op) 
{
    switch(op) {
        case '+': 
        case '-': return 1;
        case 'x': 
        case '/': return 2;
        default: return -1;
    }
}

string to_postfix(string& expr) {
    OpStack ops;
    string res;
    res.reserve(expr.size() * 2);
    
    for (int i = 0; i < expr.size(); i++) 
    {
        char c = expr[i];
        if (isdigit(c)) {
            while (i < expr.size() && isdigit(expr[i])) 
            {
                res += expr[i++];
            }
            i--;
            res += " ";
        } 
        else if (c == '+' || c == '-' || c == 'x' || c == '/') {
            while (!ops.empty() && getPrecedence(ops.top()) >= getPrecedence(c)) {
                res += ops.pop();
                res += " ";
            }
            ops.push(c);
        }
    }

    while (!ops.empty()) {
        res += ops.pop();
        res += " ";
    }
    return res;
}

string calc(string& a, string& b, char op) {
    switch (op) {
        case '+': return add(a, b);
        case '-': return compareStrings(a, b) >= 0 ? sub(a, b) : "0";
        case 'x': return mul(a, b);
        case '/': return div(a, b);
        default : return "INVALID OP";
    }
}

string evaluatePostfix(string& postfix) {
    if (postfix.empty()) return "0";

    StringStack operands;
    string token;
    token.reserve(20);

    for (char ch : postfix) {
        if (isspace(ch)) {
            if (!token.empty()) {
                operands.push(token);
                token.clear();
            }
        }
        else if (isdigit(ch)) {
            token += ch;
        } 
        else if (ch == '+' || ch == '-' || ch == 'x' || ch == '/') {
            string b = operands.pop();        
            string a = operands.pop();    
            operands.push(calc(a, b, ch));
        }
    }

    if (!token.empty())
        operands.push(token);

    return operands.pop();
}

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);
    cout.tie(nullptr);
    int t;
    cin >> t;

    while (t--) {
        int n;
        cin >> n;

        if (n == 1) {
            string s;
            cin >> s;
            string postfix = to_postfix(s);
            cout << evaluatePostfix(postfix) << endl;
        }
        else if (n == 2) {
            string base, exponent;
            cin >> base >> exponent;
            cout << exp(base, exponent) << '\n';
        }
        else if (n == 3) {
            string a, b;
            cin >> a >> b;
            cout << gcd(a, b) << '\n';
        }
        else if (n == 4) {
            string s;
            cin >> s;
            cout << fact(s) << '\n';
        }
    }
    return 0;
}