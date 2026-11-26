/**
 * form_input: a value set on a form's element by the ref a read_page gave, as the element takes it.
 */
import type { Page } from "playwright-core";

import { REF_ACTION_MS, element } from "./pointer.ts";
import { PageRefusal } from "./refusal.ts";

/** What the member's failure adds: the values each kind of element takes. */
export const FORM_VALUES = "a boolean sets a checkbox or radio button, a select takes an option's value or text, a text field any text";

/**
 * A boolean checks or unchecks; a select picks the option whose value or text the value is; any
 * other element is filled with the value as text.
 */
export async function formInput(page: Page, ref: string, value: string | number | boolean): Promise<void> {
  const field = await element(page, ref);
  const options = { timeout: REF_ACTION_MS };
  if (typeof value === "boolean") {
    await field.setChecked(value, options);
    return;
  }
  const text = String(value);
  const kind = await field.evaluate(
    (el, wanted) => {
      if (!(el instanceof HTMLSelectElement)) return "field";
      return [...el.options].some((o) => o.value === wanted || o.label === wanted) ? "select" : "no option";
    },
    text,
    options,
  );
  // Playwright's selectOption waits for an option that is not there until it times out.
  if (kind === "no option") throw new PageRefusal(`${ref} has no option ${JSON.stringify(text)}: ${FORM_VALUES}.`);
  if (kind === "select") await field.selectOption(text, options);
  else await field.fill(text, options);
}
