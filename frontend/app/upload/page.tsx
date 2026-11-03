import { AppShell } from "@/components/AppShell";
import { UploadStudio } from "@/components/UploadStudio";

export default function UploadPage() {
  return (
    <AppShell
      title="Create from YouTube"
      subtitle="Paste a video link and let ClipKaro find its strongest moments."
    >
      <UploadStudio />
    </AppShell>
  );
}
