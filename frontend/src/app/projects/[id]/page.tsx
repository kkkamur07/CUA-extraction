import { VideoWorkbench } from "@/components/VideoWorkbench";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ file?: string }>;
};

export default async function ProjectPage({ params, searchParams }: Props) {
  const { id } = await params;
  const query = await searchParams;
  const videoName = query.file || `${id}.mp4`;

  return <VideoWorkbench id={id} videoName={videoName} />;
}
