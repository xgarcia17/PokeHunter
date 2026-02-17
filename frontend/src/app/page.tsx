import NavBar from "@/components/navbar";
import Scanner from "@/components/scanner";

export default function ScannerPage() {
  return (
    <div className="h-screen bg-gradient-to-br from-purple-100 via-blue-50 to-purple-50 flex flex-col overflow-hidden">
      {/* Navigation Bar */}
      <NavBar />
      {/* Main Content of Page : Scanner */}
      <div className="flex-1 overflow-auto max-w-7xl mx-auto w-[80%] px-8 py-6">
        <Scanner />
      </div>
    </div>
  );
}
