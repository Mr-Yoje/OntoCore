import { describe, expect, it } from "vitest";
import { providerSaveTip } from "./providerDraft";

const blank = {
  label: "",
  prefix: "openai",
  api_base: "",
  api_key: "",
};

describe("providerSaveTip", () => {
  it("asks for name, base url and api key when creating empty", () => {
    expect(providerSaveTip(blank, "create")).toBe("请填写名称、Base URL、API Key");
  });

  it("treats whitespace as empty", () => {
    expect(
      providerSaveTip({ ...blank, label: "  ", api_base: " \n", api_key: "   " }, "create"),
    ).toBe("请填写名称、Base URL、API Key");
  });

  it("allows edit to keep an existing key", () => {
    expect(
      providerSaveTip(
        { label: "DeepSeek", prefix: "deepseek", api_base: "https://api.deepseek.com", api_key: "", has_api_key: true },
        "edit",
      ),
    ).toBeNull();
  });

  it("still requires a key when editing a vendor that never saved one", () => {
    expect(
      providerSaveTip(
        { label: "DeepSeek", prefix: "deepseek", api_base: "https://api.deepseek.com", api_key: "" },
        "edit",
      ),
    ).toBe("请填写API Key");
  });

  it("does not require a test model", () => {
    expect(
      providerSaveTip(
        { label: "A", prefix: "openai", api_base: "https://example.com", api_key: "sk" },
        "create",
      ),
    ).toBeNull();
  });
});
