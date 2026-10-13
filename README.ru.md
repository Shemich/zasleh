# Zasleh

**Инструменты Arma 3 для 3ds Max**: импорт и экспорт моделей `.p3d`, именованные selections, точки
памяти, материалы и `.rvmat`, `model.cfg`. То, ради чего раньше открывали Object Builder, — прямо в 3ds Max.

[Документация](https://shemich.github.io/zasleh/) (на английском) · [English](README.md)

*Zasleh* — так в моделях BI называется selection вспышки выстрела.

## Возможности

- **p3d туда и обратно без потерь.** Модель после импорта и экспорта — те же точки, грани, нормали,
  UV-наборы, selections, свойства и масса. Проверено на 47 моделях, включая Arma 3 Samples.
- **Selections, которые переживают моделирование.** Cut, extrude, weld, attach, detach — они остаются.
  Веса, «find components», проверки, собственный Undo.
- **Наборы имён.** На что обычно делят танк, машину, дом — с пояснением к каждому имени. Чего у объекта
  ещё нет, показано списком; двойной клик назначает выделенные полигоны.
- **Текстуры и материалы.** Текстура и `.rvmat` для selection, как в Object Builder. Генерация `.rvmat`
  (Super, NormalSpecular, Detail, Glass). Текстуры `.paa` во вьюпорте.
- **LOD'ы — слои**, со своими именованными свойствами. Прокси, колёса или башню можно получить отдельными объектами.
- **model.cfg**: скелет, секции, анимации; готовые файлы читаются с наследованием.
- **Быстро.** Танк на 145 МБ с 11 LOD'ами: около 6 секунд импорт, около 7 экспорт.
- Бинаризованные модели — через ваш дебинаризатор. Multi-structure здания.

## Установка

1. Скачайте репозиторий и положите папку туда, где держите инструменты.
2. Запустите `install.bat` (от администратора, если он не может писать в папку 3ds Max).
3. В 3ds Max: *Customize > Customize User Interface > Toolbars*, категория **Zasleh** — перетащите
   действие на панель инструментов и нажмите.

Нужен 3ds Max 2024, больше ничего. Подробнее — в [документации](https://shemich.github.io/zasleh/installation.html).

## Разработчикам

```
scripts/Zasleh/python/atb_p3d    форматы, 3ds Max не нужен: p3d, paa, rvmat, model.cfg
scripts/Zasleh/python/atb_max    сцена: импорт, экспорт, selections, материалы...
scripts/Zasleh/python/atb_max/ui панель на Qt, по файлу на вкладку
scripts/Zasleh/python/tests      юнит-тесты и проверки, идущие внутри 3ds Max без интерфейса
docs/                            сайт документации
```

    cd scripts\Zasleh\python
    python -m unittest discover -s tests -t .
    python -m atb_p3d info model.p3d
    python -m atb_p3d diff a.p3d b.p3d

## Спасибо

Soul_Assassin: его ArmA Toolbox много лет назад показал, что всему этому место внутри 3ds Max.
