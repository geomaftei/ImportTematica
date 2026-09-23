# Introducere Tematica in Pentana – varianta Python

Port al robotului UiPath **IntroducereTematicaFramework** (REFramework, v1.0.7). Procesul citește matricea de
tematică `MatriceDeIntrodus.xlsx` din folderul de proiect și o introduce în aplicația desktop
**Ideagen Pentana Audit MK12** (`pentanamk.exe`): procese / arii / sub-arii în Universul de procese, apoi un șablon
cu riscuri, controale și teste, salvat cu copie de siguranță.

Partea de preluare din Exchange a robotului original nu a fost portată (la cerere): fișierul se pune direct în
folderul de proiect.

## Corespondența cu proiectul UiPath

| UiPath | Python |
|---|---|
| `Main.xaml` (state machine REFramework) | `tematica/framework.py` + `main.py` |
| `Framework/InitAllSettings.xaml` (Config.xlsx + Assets) | `config.yaml` + `tematica/config.py` (credențiale din `.env` / variabile de mediu / keyring) |
| `Framework/SetTransactionStatus.xaml`, `TakeScreenshot.xaml`, `KillAllProcesses.xaml` | `Framework.run()` – log, captură de ecran, închidere/kill, retry |
| `Process.xaml` + secvențele "Citire Matrice" (Read Range, Filter, Remove Duplicates) | `tematica/matrice.py` (`pandas`) |
| `Pentana/LoginPentana.xaml` | `PentanaApp.login()` |
| `Pentana/IntroducereProceseInUnivers.xaml` | `tematica/pentana/univers.py` |
| `Pentana/IntroducereRiscuri.xaml` | `tematica/pentana/sabloane.py` |
| `Pentana/SalvareCopieSiguranta.xaml` | `tematica/pentana/salvare.py` |
| `Pentana/StergereIndexProcese.xaml` (comentat în Process.xaml) | `tematica/pentana/stergere_index.py` |
| `Pentana/NumerotareTree.xaml` (neapelat) | `matrice.numeroteaza()` |
| Selectori `<wnd ctrlname=... />`, Click, Type Into, Send Hotkey | `pywinauto` (backend UIA) – vezi antetul din `tematica/pentana/app.py` |
| **Click Image** (imaginile `TargetImageBase64` din .xaml) | `Data/Images/*.png` + `tematica/pentana/images.py` (`pyautogui` + OpenCV, Accuracy 0.8) |

Imaginile din `Data/Images` sunt exact cele pe care le căuta robotul, extrase din fișierele `.xaml`
(`manifest.json` spune de unde vine fiecare). Căutarea se face în dreptunghiul controlului pe care robotul îl avea
ca *scope* în selector, iar dacă imaginea nu este găsită se folosește controlul după `auto_id` ca rezervă.

## Instalare

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Verifică `config.yaml`: calea către `pentanamk.exe`, numele șablonului, entitatea. Dacă Pentana cere autentificare
la pornire, copiază `.env.example` în `.env` și completează `PENTANA_USER` / `PENTANA_PASSWORD`.

## Rulare

Pune `MatriceDeIntrodus.xlsx` în folderul de proiect, apoi:

```bash
python main.py
```

Alte variante:

```bash
python main.py --dry-run                     # doar verifică Excel-ul și afișează arborele Proces > Arie > Sub-arie > Risc > Control > Test
python main.py --file alta_matrice.xlsx      # altă matrice
python main.py --only riscuri --attach       # un singur pas, pe o instanță Pentana deja deschisă și autentificată
python tools/genereaza_exemplu.py            # scrie o matrice de exemplu în Data/Input/
```

Pentru a sări peste crearea Universului de procese (când a fost deja introdus), pune în `config.yaml`
`framework.sari_peste_univers: true` – aplicația pornește și trece direct la crearea șablonului.

Teste (partea de date, fără Pentana): `pytest`.

## Formatul matricei (Sheet1)

Coloane obligatorii: `Cod referinta APR (Nr. Crt.)` (prima coloană; se scrie la fiecare test, în câmpul `CodApr:` de pe
tab-ul „Tehnici De Testare”), `Proces`, `Arie`, `SubArie`, `Descriere Risc`, `Tip Risc`, `Denumire Control`,
`Descriere Control (Criterii)`, `Tip Control`, `Frecventa Control`, `Cadru de reglementare Control (Criterii)`, `Denumire Test`,
`Tehnici de Testare`, `Detalii Tehnici de Testare`, `Auditor alocat`, `Termen finalizare test` (ultimele două
se completează la fiecare test pe tab-ul „Tehnici De Testare”: auditorii se bifează în lista `ResponsabilTest:` -
numele se potrivesc tolerant, iar cele negăsite sau ambigue sunt raportate în log -, iar termenul, de forma
zz.ll.aaaa, se pune în câmpul-calendar `Termen finalizare test`). Un rând = un test; celelalte niveluri se deduc prin
eliminarea duplicatelor, exact ca în robot. `SubArie` gol înseamnă că riscul este atașat direct ariei.

## Ce trebuie verificat pe aplicația reală

Logica de date este testată; partea de UI a fost transpusă din selectorii și imaginile robotului, dar nu a putut fi
rulată pe Pentana. Puncte de urmărit la prima rulare (`tools/inspect_pentana.py` afișează arborele de controale al
unei ferestre, ca UI Explorer):

1. **Rezoluție / scalare.** Imaginile au fost capturate la scalarea ecranului robotului; la altă scalare (125 %,
   150 %) potrivirea poate eșua – atunci fie se recapturează imaginile, fie se lasă rezervele după `auto_id`.
2. **Listele de răspunsuri** (`m_AnswerLists`): elementele „Functionalitatea de control” (control) și „Exceptii”
   (test) – numele vin din textul activităților UiPath (`pentana.control_answer_list`, `pentana.test_answer_list`).
3. **Celula din matricea risc/control** și meniul contextual `c_RCMatrixContext` – robotul dădea două clicuri;
   aici click, apoi imaginea „Creare legătură…”, apoi click dreapta ca rezervă.
4. **Selectarea nodului în arborele de procese** (`pb_EditInclusion`) – robotul apăsa „săgeată dreapta” de 1–2 ori;
   aici nodul se alege după nume și se confirmă cu Enter.
5. **Bifarea tehnicilor de testare** – click pe element + `toggle()`/SPACE.
6. **Prefixul „1”** pus înaintea numelui fiecărui proces (activitatea „Adauga '1' inaintea numelui de Proces”) –
   este reprodus; scoate-l din `pentana.process_name_prefix` dacă nu este dorit.

La orice eroare de sistem se creează `Data/Exceptions_Screenshots/ExceptionReport_<data>.zip` cu tot ce trebuie
pentru diagnosticare: `captura.png` (ecranul în momentul erorii), `raport.txt` (eroarea, selectorul căutat,
traceback, ferestrele Pentana deschise), `controale.txt` (arborele de controale al ferestrei principale, ca în
UI Explorer) și `log.txt` (ultimele linii din log). Folderul păstrează doar ultimul pachet. Trimite acest zip când
ceva nu merge.
