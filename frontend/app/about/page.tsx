import type { Metadata } from "next";
import { AboutExperience } from "./AboutExperience";

export const metadata: Metadata = {
  title: "About ClipKaro — AI video intelligence built for creators",
  description:
    "Discover why ClipKaro was built, how its AI media pipeline works, the principles behind the product, and the story of founder Faik Hameed Mulla.",
};

export default function AboutPage() {
  return <AboutExperience />;
}
