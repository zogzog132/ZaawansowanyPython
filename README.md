# PyFlow

Biblioteka do definiowania, planowania i uruchamiania przepływów danych opartych na skierowanych grafach acyklicznych (DAG).

## Instalacja

Wymagany Python 3.10+.

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Uruchamianie testów

Z katalogu głównego repozytorium:

```powershell
python -m pytest
```

Testy jednostkowe: `tests/test_models.py`, `tests/test_graph.py`, `tests/test_engine.py`, `tests/test_report.py`.
Test integracyjny (CSV -> JSON): `tests/test_integration.py`.

## Struktura projektu

Kod jest podzielony na trzy niezależne warstwy: **model**, **planowanie** i **wykonanie**.

| Plik | Odpowiedzialność |
|---|---|
| `src/pyflow/models.py` | Model: `Task`, `Workflow`, `WorkflowValidationError` (Lab 1) |
| `src/pyflow/graph.py` | Planowanie: `topological_order`, `execution_layers` (Lab 1) |
| `src/pyflow/results.py` | Model wyniku: `TaskStatus`, `TaskState`, `RunResult`, `TaskExecutionError` |
| `src/pyflow/engine.py` | Wykonanie: `run(workflow)` |
| `src/pyflow/report.py` | Tekstowy raport czasów: `format_report(result)` |
| `examples/sales_pipeline.py` | Przykład end-to-end CSV -> JSON |

`Workflow` nie wywołuje funkcji zadań – robi to wyłącznie silnik, który korzysta z publicznego planera `topological_order` z Lab 1.

## Przykład użycia

### Planowanie (Lab 1)

```python
from pyflow import Task, Workflow, execution_layers, topological_order

def step(inputs, params):
    return None

wf = Workflow()
wf.add_task(Task("extract", step))
wf.add_task(Task("clean_a", step, dependencies=["extract"]))
wf.add_task(Task("clean_b", step, dependencies=["extract"]))
wf.add_task(Task("report", step, dependencies=["clean_a", "clean_b"]))

wf.validate()
print("Kolejność topologiczna:", topological_order(wf))
# ['extract', 'clean_a', 'clean_b', 'report']

print("Warstwy wykonania:", execution_layers(wf))
# [['extract'], ['clean_a', 'clean_b'], ['report']]
```

### Wykonanie (Lab 2)

```python
from pyflow import Task, Workflow, format_report, run

wf = Workflow()
wf.add_task(Task("extract", lambda inputs, params: 10))
wf.add_task(Task("clean_a", lambda inputs, params: inputs["extract"] + params["add"],
                 dependencies=["extract"], params={"add": 1}))
wf.add_task(Task("clean_b", lambda inputs, params: inputs["extract"] * 2,
                 dependencies=["extract"]))
wf.add_task(Task("report", lambda inputs, params: inputs["clean_a"] + inputs["clean_b"],
                 dependencies=["clean_a", "clean_b"]))

result = run(wf)
result.outputs["report"]                # 31
result.task_states["report"].status     # TaskStatus.SUCCEEDED
result.task_states["report"].duration   # czas w sekundach
result.succeeded                        # True
print(format_report(result))
```

## Kontrakt funkcji zadania

Każda funkcja zadania ma postać `function(inputs, params)`:

* `inputs` – mapowanie *nazwa bezpośredniej zależności -> jej wynik*. Zadanie dostaje **wyłącznie** wyniki swoich bezpośrednich zależności (bez przechodnich). Zadanie bez zależności dostaje puste mapowanie.
* `params` – mapowanie parametrów skonfigurowanych w `Task(params=...)`.
* Wartość zwrócona przez funkcję staje się wynikiem zadania (`result.outputs[nazwa]`).
* Obie mapy są tylko do odczytu (`MappingProxyType`). Zadania nie powinny modyfikować obiektów otrzymanych w `inputs` – są to te same obiekty, które dostają inne zadania zależne.
* Zgłoszenie wyjątku oznacza awarię zadania (patrz *Polityka błędów*).

## API silnika

`run(workflow) -> RunResult`

1. Waliduje workflow (`workflow.validate()`). Błędna definicja (brakująca zależność, cykl) kończy się wyjątkiem `WorkflowValidationError` **przed** uruchomieniem jakiegokolwiek zadania.
2. Wyznacza plan publicznym planerem `topological_order(workflow)`.
3. Wykonuje zadania synchronicznie, jedno po drugim, w kolejności planu.
4. Zwraca niemutowalny `RunResult`. Pusty workflow daje poprawny pusty wynik (`succeeded == True`).

| `RunResult` | Znaczenie |
|---|---|
| `outputs` | nazwa zadania -> zwrócona wartość (tylko zadania `SUCCEEDED`) |
| `task_states` | nazwa zadania -> `TaskState`, w kolejności planu |
| `succeeded` | `True`, gdy wszystkie zadania mają status `SUCCEEDED` |
| `duration` | czas całego przebiegu w sekundach (walidacja + planowanie + wykonanie) |
| `failed_tasks`, `skipped_tasks` | listy nazw zadań o danym statusie |
| `errors` | nazwa zadania -> `TaskExecutionError` |
| `raise_for_failure()` | zgłasza pierwszy `TaskExecutionError`, jeśli przebieg się nie powiódł |

| `TaskState` | Znaczenie |
|---|---|
| `status` | `TaskStatus` |
| `started_at`, `finished_at` | odczyty `time.perf_counter()` (zegar monotoniczny) albo `None` |
| `duration` | czas zadania w sekundach albo `None` dla zadań nieuruchomionych |
| `error` | `TaskExecutionError` dla zadania `FAILED`, inaczej `None` |
| `skip_reason` | dla zadania `SKIPPED`: które zależności i z jakim statusem je zablokowały |

### Statusy

| Status | Znaczenie |
|---|---|
| `PENDING` | zadanie czeka na wykonanie (stan początkowy) |
| `RUNNING` | funkcja zadania jest właśnie wykonywana |
| `SUCCEEDED` | funkcja zwróciła wynik |
| `FAILED` | funkcja zgłosiła wyjątek |
| `SKIPPED` | zadanie nie zostało uruchomione, bo któraś z jego zależności nie zakończyła się sukcesem |

Po zakończeniu `run()` każde zadanie ma status `SUCCEEDED`, `FAILED` albo `SKIPPED`.

## Polityka błędów: kontynuacja niezależnych zadań

Wybrano politykę **„dokończ niezależne zadania”** (zamiast fail-fast):

* Zadanie, którego funkcja zgłosi wyjątek, dostaje status `FAILED`.
* Zadanie, którego co najmniej jedna **bezpośrednia** zależność ma status `FAILED` lub `SKIPPED`, dostaje status `SKIPPED`, a jego funkcja nie jest wywoływana. Dzięki temu pominięcie przenosi się automatycznie na wszystkich potomków.
* Zadania, które nie zależą (bezpośrednio ani pośrednio) od nieudanego zadania, wykonują się normalnie, a ich wyniki trafiają do `outputs`.

Uzasadnienie: jeden przebieg daje maksimum informacji (wszystkie niezależne błędy i wszystkie możliwe wyniki naraz), a reguła zależy wyłącznie od struktury grafu, nie od kolejności wykonania – zachowa więc ten sam sens po dodaniu współbieżności.

**Diagnostyka.** Błąd funkcji zadania jest opakowywany w `TaskExecutionError` z nazwą zadania (`error.task_name`), a oryginalny wyjątek jest zachowany jako przyczyna (`error.__cause__`) dzięki konstrukcji `raise TaskExecutionError(...) from exc`. Silnik nie wypisuje błędów na ekran – zapisuje je w `RunResult`. Kto woli wyjątek niż sprawdzanie wyniku, wywołuje `result.raise_for_failure()`.

Silnik przechwytuje `Exception` tylko na granicy wywołania funkcji użytkownika i nigdy go nie tłumi (trafia do wyniku razem z przyczyną). `KeyboardInterrupt` i `SystemExit` nie są przechwytywane.

## Raport tekstowy

`format_report(result)` zwraca tabelę ze statusem i czasem każdego zadania oraz sumą czasów zadań i czasem całego przebiegu. Raport tylko odczytuje `RunResult` – nie zmienia wyników.

## Przykład end-to-end: CSV -> JSON

`examples/sales_pipeline.py` wczytuje `examples/data/sales.csv`, waliduje rekordy (błędne trafiają do sekcji `rejected` z numerem linii i powodem), agreguje sprzedaż po regionie i po produkcie, a następnie zapisuje raport JSON. Obie agregacje używają tej samej funkcji `aggregate` z różnymi `params` (`{"group_by": "region"}` / `{"group_by": "product"}`).

```
read_csv -> clean_records -> aggregate_by_region  -> write_json_report
                          -> aggregate_by_product ->
```

Uruchomienie z katalogu głównego repozytorium:

```powershell
python -m examples.sales_pipeline
# lub z własnymi ścieżkami:
python -m examples.sales_pipeline wejscie.csv wyjscie.json
```

Domyślnie raport trafia do `examples/output/sales_report.json` (katalog ignorowany przez Git). Przykład jest deterministyczny (posortowane klucze JSON, kwoty liczone na `Decimal`) i nie wymaga sieci. Przykładowy wynik w konsoli:

```
Raport przebiegu PyFlow
==========================================
Zadanie               Status     Czas [ms]
------------------------------------------
read_csv              SUCCEEDED      0.079
clean_records         SUCCEEDED      0.047
aggregate_by_product  SUCCEEDED      0.023
aggregate_by_region   SUCCEEDED      0.012
write_json_report     SUCCEEDED      0.269
------------------------------------------
Suma czasów zadań:  0.430 ms
Cały przebieg:      0.483 ms
Wynik: SUKCES (5/5 zadań zakończonych sukcesem)
```

Przy błędzie (np. brak pliku wejściowego) `read_csv` ma status `FAILED`, pozostałe zadania `SKIPPED`, a raport pokazuje przyczynę błędu i powód każdego pominięcia; program kończy się kodem 1.

## Algorytm i złożoność obliczeniowa

Do sortowania topologicznego oraz wyznaczania warstw wykonania wybrano **algorytm Kahna** (oparty na stopniach wejściowych wierzchołków `in-degree`):
1. Naturalnie grupuje zadania o zerowym stopniu wejściowym w kolejne warstwy równoległe (`execution_layers`).
2. Wykrywa cykle bez ryzyka przepełnienia stosu rekurencji (jeśli liczba odwiedzonych węzłów jest mniejsza niż liczba wszystkich zadań, w grafie istnieje cykl).
3. Determinizm uzyskano poprzez sortowanie alfabetyczne zadań wewnątrz każdej warstwy.

* **Złożoność czasowa:** O(V log V + E), gdzie V to liczba zadań, a E to liczba zależności (czynnik log V wynika z sortowania alfabetycznego warstw w celu zachowania deterministycznej kolejności).
* **Złożoność pamięciowa:** O(V + E) na przechowanie listy sąsiedztwa oraz stopni wejściowych.

Silnik wykonawczy dokłada O(V + E): każde zadanie jest uruchamiane co najwyżej raz, a każda zależność sprawdzana raz przy budowaniu `inputs`.