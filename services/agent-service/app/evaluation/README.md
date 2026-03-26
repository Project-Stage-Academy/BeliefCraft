# Agent Evaluation Framework

Evaluation framework для вимірювання продуктивності warehouse advisor агента.

## Структура

```
app/evaluation/
├── __init__.py           # Експорти моделей
├── models.py             # Pydantic моделі для evaluation
├── evaluator.py          # Основний клас AgentEvaluator
├── cli.py                # CLI для запуску evaluations
├── __main__.py           # Entry point для CLI модулю
└── test_scenarios.yaml   # Golden dataset з 20 тест-сценаріями
```

## Golden Dataset

Dataset містить **20 сценаріїв** різної складності:

- **Easy (15 сценаріїв, 3 ітерації)**: Базові запити (inventory, suppliers, POs, shipments, products)
- **Medium (3 сценарії, 5 ітерацій)**: Risk assessment, constrained optimization, sensor reconciliation
- **Hard (2 сценарії, 8 ітерацій)**: POMDP belief estimation, multi-constraint optimization

## Метрики

Кожен сценарій оцінюється за 5 метриками (0-1):

1. **Retrieval Accuracy (30%)**: Чи знайшов агент правильний algorithm/data
2. **Citation Quality (20%)**: Коректність та повнота citations
3. **Code Validity (15%)**: Чи парситься код та чи має сенс
4. **Reasoning Quality (15%)**: Логічність reasoning trace
5. **Actionability (20%)**: Специфічність та виконуваність recommendations

**Overall Score**: Зважена середня метрик. Сценарій вважається **passed** якщо:
- Overall score ≥ 0.7
- Status = "completed"
- Немає failure reasons

## Використання

### CLI команди

**Локально (в сервісі):**

```bash
# Список всіх сценаріїв
uv run python -m app.evaluation.cli list

# Деталі конкретного сценарію
uv run python -m app.evaluation.cli show scenario_001_inventory_low_stock

# Запуск всіх сценаріїв
uv run python -m app.evaluation.cli run

# Запуск конкретного сценарію
uv run python -m app.evaluation.cli run -s scenario_001_inventory_low_stock

# Запуск кількох сценаріїв з кастомним output файлом
uv run python -m app.evaluation.cli run -s scenario_001 -s scenario_002 -o report.json

# Кастомний файл зі сценаріями
uv run python -m app.evaluation.cli run -f /path/to/custom_scenarios.yaml -o report.json

# Комбінований приклад
uv run python -m app.evaluation.cli run \
  -s scenario_001 -s scenario_002 \
  -f ./custom_scenarios.yaml \
  -o evaluation_report_$(date +%Y%m%d).json
```

### Docker / Makefile команди

```bash
# Запуск всіх сценаріїв (зберігає в evaluation_report.json всередині контейнера)
make evaluate

# Запуск з параметрами
make evaluate ARGS="-s scenario_001_inventory_low_stock -o my_report.json"

# Запуск конкретних сценаріїв
make evaluate ARGS=" -s scenario_016_risk_order_delay"

# Список всіх сценаріїв
make evaluate-list

# Деталі сценарію
make evaluate-show ID=scenario_001_inventory_low_stock

# Прямі docker compose команди
docker compose exec agent-service /app/.venv/bin/python -m app.evaluation.cli list
docker compose exec agent-service /app/.venv/bin/python -m app.evaluation.cli run
docker compose exec agent-service /app/.venv/bin/python -m app.evaluation.cli show scenario_001
```

### Отримання звіту з контейнера

**Де зберігається звіт:**
- За замовчуванням: `/app/evaluation_report.json` всередину контейнера
- На host машині: потрібно скопіювати з контейнера

**Способи отримання звіту:**

**Варіант 1: Скопіювати з контейнера (найпростіший)**
```bash
# Запустити evaluation
make evaluate

# Скопіювати файл на host
docker compose cp agent-service:/app/evaluation_report.json ./evaluation_report.json

# Переглянути результати
cat evaluation_report.json | jq '{pass_rate, avg_overall_score, total_scenarios, passed, failed}'
```

**Варіант 2: Зберегти напряму в mounted директорію**
```bash
# app/ директорія змонтована на host, тому файл буде доступний одразу
make evaluate ARGS="-o /app/services/agent-service/app/evaluation_report.json"

# Файл з'явиться на host за адресою:
cat services/agent-service/app/evaluation_report.json | jq .
```

**Варіант 3: Запуск локально (без Docker)**
```bash
# Перейти в сервіс
cd services/agent-service

# Запустити evaluation (файл зберігається тут же)
uv run python -m app.evaluation.cli run -o evaluation_report.json

# Переглянути результати
cat evaluation_report.json | jq .
```

### CLI опції (довідка)

**Команда `run` (запуск evaluation)**
```
uv run python -m app.evaluation.cli run [OPTIONS]

Options:
  -s, --scenarios TEXT           Specific scenario IDs to run (can be multiple)
  -o, --output TEXT              Output file for JSON report
                                 (default: evaluation_report.json)
  -f, --scenarios-file PATH      Path to custom scenarios YAML file
```

**Команда `list` (список сценаріїв)**
```
uv run python -m app.evaluation.cli list [OPTIONS]

Options:
  -f, --scenarios-file PATH      Path to custom scenarios YAML file
```

**Команда `show` (деталі сценарію)**
```
uv run python -m app.evaluation.cli show SCENARIO_ID [OPTIONS]

Arguments:
  SCENARIO_ID                    ID сценарію (обов'язковий)

Options:
  -f, --scenarios-file PATH      Path to custom scenarios YAML file
```

### Програмне використання

```python
from app.evaluation.evaluator import AgentEvaluator

# Ініціалізація
evaluator = AgentEvaluator()

# Запуск evaluation
report = await evaluator.run_evaluation()

# Запуск конкретних сценаріїв
report = await evaluator.run_evaluation(
    scenario_ids=["scenario_001", "scenario_002"]
)

# Аналіз результатів
print(f"Pass rate: {report.pass_rate * 100:.1f}%")
print(f"Average score: {report.avg_overall_score:.2f}")

for category, stats in report.results_by_category.items():
    print(f"{category}: {stats.pass_rate * 100:.1f}% pass rate")
```

## Додавання нових сценаріїв

Редагуйте `test_scenarios.yaml`:

```yaml
scenarios:
  - id: "scenario_NEW"
    category: "your_category"
    query: "Your test query here (min 10 characters)"
    context:
      key: "value"
    max_iterations: 3
    expected_output:
      must_include:
        algorithm: "expected pattern|another pattern"
        formula: true
        code: true
        recommendations:
          min_count: 1
          max_count: 5
      must_cite:
        chapter: [3, 4, 5]
    evaluation_criteria:
      retrieval_accuracy: "Human-readable criterion"
      actionability: "Another criterion"
    difficulty: "easy"  # easy | medium | hard
```

## Звіти

Evaluation генерує JSON звіт з:

- Aggregated metrics (pass rate, avg scores)
- Results by category
- Results by difficulty
- Детальні результати кожного сценарію
- Failed scenarios з failure reasons

Приклад структури:

```json
{
  "report_id": "uuid",
  "total_scenarios": 20,
  "passed": 18,
  "failed": 2,
  "pass_rate": 0.9,
  "avg_retrieval_accuracy": 0.85,
  "avg_citation_quality": 0.78,
  "avg_code_validity": 0.92,
  "avg_reasoning_quality": 0.81,
  "avg_actionability": 0.87,
  "avg_overall_score": 0.84,
  "results_by_category": {...},
  "results_by_difficulty": {...},
  "failed_scenarios": [...],
  "results": [...]
}
```

## Тести

```bash
# Запуск тестів evaluation framework
uv run pytest services/agent-service/tests/test_evaluation*.py -v

# З coverage
uv run pytest services/agent-service/tests/test_evaluation*.py --cov=app.evaluation
```

## Troubleshooting

### Сценарій завжди fails

1. Перевірте що `expected_output.must_include` не занадто строгий
2. Перегляньте `full_response` у результаті для debug
3. Перевірте що `max_iterations` достатньо для складності запиту

### Low scores

- **Retrieval Accuracy**: Агент не знаходить потрібний algorithm → покращити промпти або RAG
- **Citation Quality**: Немає або неправильні citations → покращити citation extraction
- **Code Validity**: Syntax errors → покращити code generation
- **Reasoning Quality**: Короткий trace або немає аналізу → збільшити iterations
- **Actionability**: Розпливчасті recommendations → покращити рекомендаційні промпти

## Best Practices

1. **Realistic queries**: Базуйте сценарії на дійсних даних проекту
2. **Balanced difficulty**: Підтримуйте баланс easy/medium/hard сценаріїв
3. **Clear criteria**: Evaluation criteria мають бути специфічними
4. **Regular runs**: Запускайте evaluation після змін промптів/моделей
5. **Track changes**: Зберігайте історію reports для tracking improvements
