import { AppShell } from "@/components/AppShell";
import { UploadStudio } from "@/components/UploadStudio";

export default function UploadPage() {
  return (
    <AppShell
      title="Create clips"
      subtitle="Upload a video or paste a YouTube link. Uploading is the most reliable option."
    >
      <UploadStudio />
    </AppShell>
  );
}
