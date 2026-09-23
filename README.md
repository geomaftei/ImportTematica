# Import Tematică în Pentana

Robot Python care citește matricea de tematică `MatriceDeIntrodus.xlsx` și o introduce în **Ideagen Pentana Audit
MK12** (`PentanaMK.exe`):

1. **Universul de procese** – procesele, ariile și sub-ariile noi (Instrumente → Configurare → Proces/Aria/Sub Aria).
2. **Șablonul de tematică** – creează șablonul (nume, entitate asociată, tip audit), apoi pentru fiecare arie /
   sub-arie: riscuri, controale, legătura risc–control și testele, cu tehnicile de testare, auditorii alocați,
   termenul de finalizare și codul APR.
3. **Salvarea** – salvează și închide șablonul, apoi face *Copie de siguranță securizată* și o confirmă.

La final, logul se încheie cu un **rezumat al rulării**: ce s-a introdus și ce trebuie verificat (auditori
negăsiți, termene nepuse, nume potrivite doar parțial).

Proiectul a pornit ca port al robotului UiPath *IntroducereTematicaFramework*; proiectul UiPath original a fost
păstrat doar în istoricul git (commit `cd12a59`, folderul `uipath/`).

## Cerințe

- Windows 10/11, Python 3.11+ și Pentana instalat pe același calculator.
- Pentru lista de auditori, motorul OCR din Windows (vine cu pachetul de limbă; se folosește româna, altfel limba
  utilizatorului).
- În timpul rulării nu folosi mouse-ul și tastatura: robotul lucrează direct în fereastra Pentana.

## Instalare

Clonează proiectul (nu descărca zip-ul – cu o clonă, actualizările vin cu `git pull`):

```bash
git clone https://github.com/geomaftei/ImportTematica.git
```
```bash
cd ImportTematica
```
```bash
pip install -r requirements.txt
```

Verifică `config.yaml` (vezi mai jos). Dacă Pentana cere autentificare la pornire, copiază `.env.example` în `.env`
și completează `PENTANA_USER` / `PENTANA_PASSWORD` (altfel se așteaptă autentificarea automată).

## Rulare

Pune `MatriceDeIntrodus.xlsx` în folderul proiectului, apoi:

```bash
python main.py
```

| Comandă | Ce face |
|---|---|
| `python main.py --dry-run` | Doar citește Excel-ul și afișează arborele Proces > Arie > Sub-arie > Risc > Control > Test, cu auditorii, termenul și codul APR – fără Pentana. Bun de rulat înainte, ca verificare. |
| `python main.py --file alta_matrice.xlsx` | Altă matrice. |
| `python main.py --only riscuri salvare` | Doar pașii dați (`univers`, `riscuri`, `salvare`). |
| `python main.py --only salvare --attach` | Pe o instanță Pentana deja deschisă (ex. doar copia de siguranță, cu lista de șabloane afișată). |
| `python tools/analiza_timp.py` | Unde s-a dus timpul în ultima rulare (fără date din matrice – rezultatul se poate trimite mai departe). |
| `python tools/genereaza_exemplu.py` | Scrie o matrice de exemplu în `Data/Input/`. |
| `pytest` | Testele pentru partea de date (matrice, potrivirea numelor, datele) – fără Pentana. |

## Configurare (`config.yaml`)

| Parametru | Implicit | Rol |
|---|---|---|
| `pentana.exe` | `C:\Program Files (x86)\Ideagen\...\PentanaMK.exe` | Aplicația pornită. |
| `pentana.template_name` | `! Tematica Import Aplicatie` | Numele șablonului creat. |
| `pentana.entity_link` | `Banca Transilvania - Procese` | Entitatea asociată (bifată). |
| `pentana.audit_type` | `Asigurare` | Tipul de audit conexat (bifat). |
| `pentana.process_name_prefix` | `1` | Prefixul pus înaintea numelui fiecărui proces (îl aduce primul în liste). |
| `pentana.process_sibling_node` | `Archived` | Nodul de pe primul nivel lângă care se adaugă primul proces. |
| `pentana.action_delay_s` | `0.4` | Pauza după fiecare clic (mai mică = mai rapid, dar Pentana trebuie să apuce să reacționeze). |
| `pentana.celula_matrice_100` | `[268, 251]` | Poziția pătrățelului risc × control în matrice, la scalarea 100% (se scalează automat). |
| `framework.sari_peste_univers` | `false` | `true` = sare peste Universul de procese (când a fost deja introdus). `--only` are prioritate. |
| `images.enabled` | `false` | `false` = acolo unde există și un selector, nu se mai caută imaginile robotului UiPath. |
| `debug.tree_depth` | `16` | Adâncimea arborelui de controale din pachetul de diagnostic. |

## Formatul matricei (Sheet1)

Un rând = un test; procesele, ariile, riscurile și controalele se deduc prin eliminarea duplicatelor. Coloanele se
caută după nume (ordinea nu contează).

| Coloană | Unde ajunge |
|---|---|
| `Cod referinta APR (Nr. Crt.)` | Test, tab „Tehnici De Testare”, câmpul `CodApr:` |
| `Proces`, `Arie`, `SubArie` | Universul de procese; alegerea nodului în șablon. `SubArie` gol = riscul e pe arie. |
| `Descriere Risc`, `Tip Risc` | Editorul de risc |
| `Denumire Control`, `Descriere Control (Criterii)`, `Tip Control`, `Frecventa Control`, `Cadru de reglementare Control (Criterii)` | Editorul de control |
| `Denumire Test`, `Tehnici de Testare`, `Detalii Tehnici de Testare` | Editorul de test |
| `Auditor alocat` | Test, lista `ResponsabilTest:` – se bifează toți auditorii din celulă |
| `Termen finalizare test` | Test, calendarul `Termen finalizare test` |

- **Auditori:** mai mulți în aceeași celulă, separați prin `,` `;` sau pe rânduri noi (Alt+Enter). Numele se
  potrivesc tolerant cu lista din Pentana (ordine nume/prenume, diacritice, inițiale, greșeli mici). Un nume care
  nu se găsește sigur (negăsit sau ambiguu, ex. doar „George” când în listă sunt doi) **nu se bifează** și apare în
  rezumat. Cel mai sigur: prenume + nume.
- **Termen:** `zz.ll.aaaa` (ex. `08.09.2026`), sau o celulă de tip dată din Excel.
- Numele vechi ale coloanelor (`Descriere Control`, `Cadru de reglementare Control`) sunt acceptate în continuare;
  lipsa coloanelor noi (cod APR, auditor, termen) dă doar un avertisment, câmpurile rămân goale.

## Loguri și diagnostic

- `logs/` – un fișier pentru fiecare rulare (`<data>_<ora>_IntroducereTematica.log`), încheiat cu rezumatul:
  *FINALIZAT CU SUCCES*, *FINALIZAT CU PROBLEME DE VERIFICAT* sau *EȘUAT*. Lista completă de utilizatori din
  Pentana nu se scrie în log.
- `Data/Exceptions_Screenshots/ExceptionReport_<data>.zip` – la o eroare: `captura.png` (ecranul), `raport.txt`
  (eroarea, traceback, ferestrele deschise), `controale.txt` (arborele de controale, cu coordonate) și `log.txt`.
  Se păstrează doar ultimul pachet; trimite-l când ceva nu merge.
- Dacă programul stă pe loc mai mult de 45 s, logul arată linia din cod la care a rămas.

## Cum funcționează (tehnic)

- **Selectori rapizi** (`tematica/pentana/fastspec.py`): pywinauto citea tot subarborele la fiecare căutare
  (inclusiv sutele de noduri din Universul de procese). `FastSpec` caută nivel cu nivel, cu un singur apel UIA pe
  element, fără să intre în arbori/liste; ferestrele Pentana se găsesc cu `EnumWindows`.
- **Liste desenate de Pentana** (utilizatorii din `ResponsabilTest:`) nu apar în UIA: se citesc prin OCR-ul din
  Windows (`tematica/pentana/ocr.py`), de sus în jos (lista e alfabetică), cu verificarea bifei pe ecran.
- **Calendarul** (`SysMonthCal32`) se setează din tastatură și se verifică din numele lui (`08/09/2026 selected.`).
- **Poziții și imagini:** unde nu există elemente UIA (pătrățelul din matrice, starea „In progres”, acțiunile de
  copie de siguranță) se folosesc poziții scalate după DPI sau imagini decupate din aplicație (`Data/Images`,
  vezi `manifest.json`), capturate la scalarea 125%.

## Structura

```
main.py                     punctul de intrare (argumente, config, log)
config.yaml                 configurarea
tematica/framework.py       orchestrarea pașilor, pachetul de diagnostic, rezumatul final
tematica/matrice.py         citirea matricei
tematica/nume_date.py       auditori (despărțire, potrivirea numelor) și termene
tematica/pentana/app.py     pornirea Pentana, ferestre, clicuri, liste
tematica/pentana/univers.py Universul de procese
tematica/pentana/sabloane.py șablonul: riscuri, controale, legături, teste
tematica/pentana/salvare.py salvarea și copia de siguranță
tools/                      analiza timpilor, matrice de exemplu, inspectarea controalelor
tests/                      teste pentru partea de date
```
