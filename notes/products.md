# Products the bakery sells

The agent's notebook (lesson 6: "notes for the next run"). Loaded into the system prompt on every
question. Keep it in sync with `mock_data.py` → PRODUCTS. Exact names as stored in `sales.article`.

| Category | Product (exact name) | Also called |
|---|---|---|
| לחמים | חלה | חלות |
| לחמים | לחם מחמצת | מחמצת |
| לחמים | לחם כוסמין | כוסמין |
| לחמים | באגט | באגטים |
| לחמים | לחם שיפון | שיפון |
| לחמניות | לחמנייה | לחמניות, לחמנייה רגילה |
| לחמניות | בייגלה ירושלמי | בייגלה, בייגלים, בייגל |
| לחמניות | לחמניית מלא | לחמניות מלאות |
| לחמניות | פוקאצ'ה אישית | פוקאצ'ה, פוקצ'ה |
| קרואסונים | קרואסון חמאה | |
| קרואסונים | קרואסון שקדים | |
| קרואסונים | פן או שוקולד | פן או שוקולה, מאפה שוקולד |
| קרואסונים | בורקס גבינה | בורקס, בורקסים |
| קונדיטוריה | אקלר | אקלרים |
| קונדיטוריה | טארט פירות | טארט, טארטים |
| קונדיטוריה | מוס שוקולד | מוס |
| קונדיטוריה | אלפחורס | |
| עוגות | עוגת שמרים | |
| עוגות | בבקה שוקולד | בבקה |
| עוגות | עוגת גבינה (פרוסה) | עוגת גבינה, עוגות גבינה |
| עוגות | רוגלך (100 גרם) | רוגלך, רוגלכים |
| עוגות | עוגיות חמאה | עוגיות |
| עונתי (ספט'–אוק') | עוגת דבש | |
| עונתי (ספט'–אוק') | חלה עגולה | |
| עונתי (נוב'–ינו') | סופגנייה | סופגניות |
| עונתי (נוב'–ינו') | לביבה מתוקה | לביבות |

How to search with `product_sales`:
- Use the shortest part of the exact name that is unique, in singular: "חלה", "בייגלה", "עוגת גבינה", "סופגנייה".
- A generic word matches several products and the tool returns each one plus a `total`: "קרואסון" → קרואסון חמאה + קרואסון שקדים; "לחם" → three breads; "עוגת" → עוגת שמרים, עוגת גבינה, עוגת דבש.
- "חלה" also matches "חלה עגולה" (seasonal). Report them separately.
- Anything not in this table (pizza, coffee, sandwiches) is not sold here: say so, and don't invent a number.
