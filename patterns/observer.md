├── CALL main_api(user_id=10, data=None)\n
│   CREATE user_id ← 10\n
│   CREATE data ← None\n
├── CALL compute(x=10, y=None)\n
│   │   CREATE x ← 10\n
│   │   CREATE y ← None\n
│   ├── CALL helper(a=10, b=None)\n
│   │   │   CREATE a ← 10\n
│   │   │   CREATE b ← None\n
│   │   │   CREATE total ← 10\n
│   │   │   ERROR ZeroDivisionError(ZeroDivisionError('division by zero'))\n
│   │   └── RETURN helper → None\n
│   │   ERROR ZeroDivisionError(ZeroDivisionError('division by zero'))\n
│   │   CREATE e ← ZeroDivisionError('division by zero')\n
│   │   ERROR UnboundLocalError(UnboundLocalError(\"cannot access local variable 'value' where it is not associat...)\n
│   └── RETURN compute → None\n
│   ERROR UnboundLocalError(UnboundLocalError(\"cannot access local variable 'value' where it is not associat...)\n
└── RETURN main_api → None