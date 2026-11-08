# Leads Generation

منصة عربية للبحث عن الشركات في السعودية والإمارات واستخراج وسائل التواصل المنشورة علنًا.

## المزايا
- بحث ويب عبر SerpAPI (Google results) أو Google Programmable Search JSON API.
- زيارة الموقع الرسمي وصفحات التواصل/من نحن لاستخراج أرقام الهاتف والبريد.
- مراعاة robots.txt، تقييد الزيارات لكل موقع، وتجاهل عناوين الشبكات المحلية والخاصة.
- حفظ النتائج ومنع التكرار الأساسي وتصدير CSV.

## إعداد محرك البحث

### الخيار الموصى به: SerpAPI
1. أنشئ حسابًا لدى SerpAPI واحصل على API Key.
2. انسخ `.env.example` إلى `.env`.
3. ضع المفتاح في `SERPAPI_KEY` واترك `SEARCH_PROVIDER=serpapi`.

### بديل: Google Programmable Search
1. أنشئ Programmable Search Engine واضبطه للبحث في الويب.
2. فعّل Custom Search JSON API في Google Cloud.
3. ضع `SEARCH_PROVIDER=google_cse` واملأ `GOOGLE_API_KEY` و`GOOGLE_CSE_ID`.

لا تضع مفاتيح API داخل ملفات GitHub أو الواجهة. أضفها في Environment Variables لدى خدمة الاستضافة.

## التشغيل على Windows

```powershell
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

افتح http://127.0.0.1:5000

## الاستخدام
اختر النشاط، الدولة (السعودية أو الإمارات)، والمدينة اختياريًا، ثم ابدأ البحث. النتائج تعتمد على ظهور الموقع في مزود البحث وعلى نشر الشركة لبيانات التواصل في صفحاتها العامة. لا يمكن ضمان رقم لكل نتيجة.

## حدود وتشغيل إنتاجي
- البحث ينفذ داخل طلب ويب متزامن؛ للإنتاج يوصى بنقله إلى طابور مهام (Celery/RQ) مع Redis، وإضافة PostgreSQL ومصادقة للمستخدمين ومحدد معدل.
- استخدم البيانات المهنية المنشورة للشركات فقط، والتزم بشروط مزود البحث والقوانين المحلية وسياسات الخصوصية والتسويق المباشر.
- لا يتجاوز المحرك حماية المواقع أو صفحات تسجيل الدخول، ولا يجمع بيانات من صفحات محظورة في robots.txt.
