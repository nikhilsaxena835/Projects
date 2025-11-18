#include <iostream>
#include <string>
using namespace std;

const int MAX_HEIGHT = 16;
const float PROB = 0.5;

int rand_height() {
    int h = 0;
    while ((rand() / float(RAND_MAX)) < PROB && h < MAX_HEIGHT) 
    {
        h++;
    }
    return h;
}

template <typename T>
struct Node {
    T val;
    int count;  
    Node** next;
    
    Node(const T& v, int height) : val(v), count(1) 
    {  
        next = new Node*[height + 1]();
    }
    
    ~Node() { delete[] next; }
};

template <typename T>
struct DefComp 
{
    bool comp(const T& a, const T& b) const 
    {
        return a < b;
    }
};

template <typename T, typename Comp = DefComp<T>>
class SkipList 
{
    Node<T>* head;
    Comp comparator;
    int curr_height;
    

    bool equal(const T& a, const T& b) const {
        return !comparator.comp(a, b) && !comparator.comp(b, a);
    }

public:
    SkipList() : curr_height(0) 
    {
        head = new Node<T>(T(), MAX_HEIGHT);
        head->count = 0;  
        srand(time(nullptr));
    }

    ~SkipList() 
    {
        auto curr = head;
        while (curr) {
            auto next = curr->next[0];
            delete curr;
            curr = next;
        }
    }

    void insert(const T& val) {
        Node<T>* update[MAX_HEIGHT + 1];
        auto curr = head;

        for (int i = curr_height; i >= 0; i--) {
            while (curr->next[i] && comparator.comp(curr->next[i]->val, val)) {
                curr = curr->next[i];
            }
            update[i] = curr;
        }

        if (curr->next[0] && equal(curr->next[0]->val, val)) {
            curr->next[0]->count++; 
            return;
        }

        int height = rand_height();
        if (height > curr_height) {
            for (int i = curr_height + 1; i <= height; i++) {
                update[i] = head;
            }
            curr_height = height;
        }

        auto new_node = new Node<T>(val, height);
        for (int i = 0; i <= height; i++) 
        {
            new_node->next[i] = update[i]->next[i];
            update[i]->next[i] = new_node;
        }
    }

    bool remove(const T& val) {
    auto curr = head;
    Node<T>* update[MAX_HEIGHT + 1];
    

    for (int i = curr_height; i >= 0; i--) {
        while (curr->next[i] && comparator.comp(curr->next[i]->val, val)) {
            curr = curr->next[i];
        }
        update[i] = curr;
    }

    curr = curr->next[0];
    if (curr && equal(curr->val, val)) {
        for (int i = 0; i <= curr_height; i++) {
            if (update[i]->next[i] != curr) break;
            update[i]->next[i] = curr->next[i];
        }

        delete curr;

        while (curr_height > 0 && !head->next[curr_height]) {
            curr_height--;
        }

        return true;
    }
    return false;
}

    bool find(const T& val) const {
        auto curr = head;
        
        for (int i = curr_height; i >= 0; i--) {
            while (curr->next[i] && comparator.comp(curr->next[i]->val, val)) {
                curr = curr->next[i];
            }
        }
        
        curr = curr->next[0];
        return (curr && equal(curr->val, val));
    }

    int count_occurrence(const T& val) const {
        auto curr = head;
        
        for (int i = curr_height; i >= 0; i--) 
        {
            while (curr->next[i] && comparator.comp(curr->next[i]->val, val)) {
                curr = curr->next[i];
            }
        }
        
        curr = curr->next[0];
        return (curr && equal(curr->val, val)) ? curr->count : 0;
    }

    T lower_bound(const T& val) const {
        auto curr = head;
        
        for (int i = curr_height; i >= 0; i--) {
            while (curr->next[i] && comparator.comp(curr->next[i]->val, val)) {
                curr = curr->next[i];
            }
        }
        
        curr = curr->next[0];
        return curr ? curr->val : T();
    }

    T upper_bound(const T& val) const 
    {
        auto curr = head;
        
        for (int i = curr_height; i >= 0; i--) {
            while (curr->next[i] && !comparator.comp(val, curr->next[i]->val)) {
                curr = curr->next[i];
            }
        }
        
        curr = curr->next[0];
        return curr ? curr->val : T();
    }

    template<typename U = T>
    typename enable_if<is_arithmetic<U>::value, T>::type
    closest_element(const T& val) const {
        if (!head->next[0]) return T();

        auto curr = head;
        
        for (int i = curr_height; i >= 0; i--) 
        {
            while (curr->next[i] && comparator.comp(curr->next[i]->val, val)) {
                curr = curr->next[i];
            }
        }
        auto before = (curr != head) ? curr : nullptr;

        auto after = curr->next[0];

        if (!after && !before) return T();
        if (!after) return before->val;
        if (!before || before == head) return after->val;

        T diff1 = abs(before->val - val);
        T diff2 = abs(after->val - val);

        return (diff1 <= diff2) ? before->val : after->val;
    }

    void print() const {
    auto curr = head->next[0]; 
    while (curr) 
    {
        for (int i = 0; i < curr->count; ++i) {
            cout << curr->val << " ";
        }
        curr = curr->next[0];
    }
    cout << endl;
}
};


int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(nullptr);
    cout.tie(nullptr);
    SkipList<int> list;
    int N;
    cin >> N;
    
    while (N > 0) {
        N--;
        int choice;
        cin >> choice;
        int value;

        if (choice == 1) {  
            cin >> value;
            list.insert(value);
        } 
        else if (choice == 2) {
            cin >> value;
            list.remove(value);
                
        } 
        else if (choice == 3) {
            cin >> value;
            if (list.find(value)) {
                cout << "1" << endl;
            } else {
                cout << "0" << endl;
            }
        } 
        else if (choice == 4) { 
            cin >> value;
            cout <<  list.count_occurrence(value) << endl;
        }
        else if (choice == 5) {
            cin >> value;
            cout << list.lower_bound(value) << endl;
        } 
        else if (choice == 6) {  
            cin >> value;
            cout << list.upper_bound(value) << endl;
        } 
        else if (choice == 7) {
            cin >> value;
            cout << list.closest_element(value) << endl;
        } 
        else {
            break; 
        }
        
        //list.print(); 
    }
    
    return 0;
}

/*



*/