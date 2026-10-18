# PyFlow

Biblioteka do definiowania i planowania przepływów danych opartych na skierowanych grafach acyklicznych (DAG).

## Instalacja

Wymagany Python 3.10+.

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Uruchamianie testów

```powershell
python -m pytest
```

## Przykład użycia

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

## Algorytm i złożoność obliczeniowa

Do sortowania topologicznego oraz wyznaczania warstw wykonania wybrano **algorytm Kahna** (oparty na stopniach wejściowych wierzchołków `in-degree`):
1. Naturalnie grupuje zadania o zerowym stopniu wejściowym w kolejne warstwy równoległe (`execution_layers`).
2. Wykrywa cykle bez ryzyka przepełnienia stosu rekurencji (jeśli liczba odwiedzonych węzłów jest mniejsza niż liczba wszystkich zadań, w grafie istnieje cykl).
3. Determinizm uzyskano poprzez sortowanie alfabetyczne zadań wewnątrz każdej warstwy.

* **Złożoność czasowa:** O(V log V + E), gdzie V to liczba zadań, a E to liczba zależności (czynnik log V wynika z sortowania alfabetycznego warstw w celu zachowania deterministycznej kolejności).
* **Złożoność pamięciowa:** O(V + E) na przechowanie listy sąsiedztwa oraz stopni wejściowych.