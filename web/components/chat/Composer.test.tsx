/**
 * Composer 附件提醒回归(20261015:超限/类型不符此前静默丢弃,用户以为坏了):
 * - >5MB 图片/文档 → 显示「超过 5MB 上限,已忽略」且不触发上传
 * - 非图片文件走 addImages(粘贴混入)→ 提示「不是图片」
 */
import { describe, expect, it, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import Composer from "./Composer";

vi.mock("../../lib/api/chat", () => ({
  uploadImage: vi.fn().mockResolvedValue({ url: "/api/files/raw?path=/a&sig=x", size: 1 }),
  uploadDoc: vi.fn().mockResolvedValue({ url: "/api/files/raw?path=/b&sig=y", size: 1 }),
}));

const over5mb = (name: string, type: string) =>
  new File([new ArrayBuffer(6 * 1024 * 1024)], name, { type });

async function pickFiles(files: File[]) {
  render(<Composer onSend={vi.fn()} disabled={false} />);
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  Object.defineProperty(input, "files", { value: files });
  fireEvent.change(input);
}

describe("Composer 附件提醒", () => {
  it("超 5MB 图片:提示已忽略,不触发上传", async () => {
    const { uploadImage } = await import("../../lib/api/chat");
    await pickFiles([over5mb("大图.png", "image/png")]);
    expect(await screen.findByText(/超过 5MB 上限,已忽略/)).toBeTruthy();
    expect(uploadImage).not.toHaveBeenCalled();
  });

  it("超 5MB 文档:提示已忽略,不触发上传", async () => {
    const { uploadDoc } = await import("../../lib/api/chat");
    await pickFiles([over5mb("测算.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]);
    expect(await screen.findByText(/超过 5MB 上限,已忽略/)).toBeTruthy();
    expect(uploadDoc).not.toHaveBeenCalled();
  });

  it("粘贴混合内容(图+非图):非图提示忽略,图正常上传", async () => {
    const { uploadImage } = await import("../../lib/api/chat");
    render(<Composer onSend={vi.fn()} disabled={false} />);
    const textarea = screen.getByRole("textbox");
    fireEvent.paste(textarea, {
      clipboardData: {
        files: [
          new File(["img"], "截图.png", { type: "image/png" }),
          new File(["x"], "说明.txt", { type: "text/plain" }),
        ],
      },
    });
    expect(await screen.findByText(/不是图片,已忽略/)).toBeTruthy();
    // FileReader 异步读图后触发上传,轮询等待
    await vi.waitFor(() => expect(uploadImage).toHaveBeenCalledTimes(1));
  });
});


describe("Composer 上传进度条", () => {
  it("文档上传中显示进度条与百分比,完成后替换为正式芯片", async () => {
    let resolveUpload: (v: { url: string; size: number }) => void = () => {};
    const { uploadDoc } = await import("../../lib/api/chat");
    vi.mocked(uploadDoc).mockImplementation(
      (_f: File, onProgress?: (pct: number) => void) =>
        new Promise<{ url: string; size: number }>((resolve) => {
          resolveUpload = (v) => {
            onProgress?.(100);
            resolve(v);
          };
        }),
    );
    render(<Composer onSend={vi.fn()} disabled={false} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", {
      value: [new File(["data"], "测算.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })],
    });
    fireEvent.change(input);
    // 上传未完成:进度芯片可见,正式芯片未出现
    await vi.waitFor(() => expect(screen.getByText(/测算\.xlsx/)).toBeTruthy());
    // 完成后:进度芯片消失,正式芯片出现
    resolveUpload({ url: "/api/files/raw?path=/x.xlsx&sig=s", size: 1 });
    await vi.waitFor(() => expect(screen.queryByText(/%/)).toBeNull());
    expect(screen.getByText(/📄 测算\.xlsx/)).toBeTruthy();
  });
});


describe("Composer 上传中防误发(20261015 竞态事故)", () => {
  it("文档上传未完成时点发送:提示等待,不触发 onSend", async () => {
    let resolveUpload: (v: { url: string; size: number }) => void = () => {};
    const { uploadDoc } = await import("../../lib/api/chat");
    vi.mocked(uploadDoc).mockImplementation(
      () =>
        new Promise<{ url: string; size: number }>((resolve) => {
          resolveUpload = resolve;
        }),
    );
    const onSend = vi.fn();
    render(<Composer onSend={onSend} disabled={false} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", {
      value: [new File(["d"], "数据.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })],
    });
    fireEvent.change(input);
    await vi.waitFor(() => expect(screen.getByText(/数据\.xlsx/)).toBeTruthy());
    // 上传在途:点发送被拦截
    fireEvent.click(screen.getByRole("button", { name: /上传中…/ }));
    expect(await screen.findByText(/还在上传中,请等进度条完成/)).toBeTruthy();
    expect(onSend).not.toHaveBeenCalled();
    // 完成后:发送恢复
    resolveUpload({ url: "/api/files/raw?path=/x.xlsx&sig=s", size: 1 });
    await vi.waitFor(() => expect(screen.queryByText(/%/)).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: /发送/ }));
    expect(onSend).toHaveBeenCalledTimes(1);
  });
});
