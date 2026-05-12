def discover_actions(page):
    """Analyse le site et retourne toutes les actions possibles"""
    actions = []

    # Trouver tous les boutons
    buttons = page.query_selector_all(
        "button, input[type='button'], input[type='submit']"
    )
    for btn in buttons:
        text = btn.inner_text() or btn.get_attribute("value") or "?"
        actions.append({"type": "button", "label": text, "element": btn})

    # Trouver tous les liens
    links = page.query_selector_all("a[href]")
    for link in links:
        text = link.inner_text()
        href = link.get_attribute("href")
        actions.append({"type": "link", "label": text, "href": href, "element": link})

    # Trouver les formulaires
    forms = page.query_selector_all("form")
    for i, form in enumerate(forms):
        actions.append(
            {"type": "form", "label": f"Formulaire #{i + 1}", "element": form}
        )

    return actions
