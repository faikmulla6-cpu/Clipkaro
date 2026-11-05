import { AppShell } from "@/components/AppShell";
import { UploadStudio } from "@/components/UploadStudio";

export default function UploadPage() {
  return (
    <AppShell
      title="Create clips"
      subtitle="Upload your original video to create Shorts. YouTube link import is coming soon."
    >
      <UploadStudio />
    </AppShell>
  );
}
